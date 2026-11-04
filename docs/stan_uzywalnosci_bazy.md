# Stan używalności bazy danych – Farmer App

Data audytu: 2026-11-04
Gałąź: `audit/database-usability` (stan wyjściowy: commit `dcbc1b4`)
Zakres: modele aplikacji `core`, migracje, schemat MySQL `farmer_db`, integralność danych,
izolacja danych użytkowników, polecenie `seed_demo_data`, konfiguracja bazy.

Audyt był wykonywany na bazie roboczej wyłącznie zapytaniami `SELECT`/`SHOW`.
Plik `.env` ani dane w `farmer_db` nie były zmieniane. Testy działały na tymczasowej
bazie `test_farmer_db`.

## 1. Aktualny stan bazy

| Parametr | Wartość |
|---|---|
| Serwer | MySQL 8.0.46 |
| Silnik tabel | InnoDB (wszystkie tabele) |
| Kodowanie / porównywanie | `utf8mb4` / `utf8mb4_unicode_ci` (baza i wszystkie tabele) |
| `sql_mode` (globalny i sesji) | `ONLY_FULL_GROUP_BY, STRICT_TRANS_TABLES, NO_ZERO_IN_DATE, NO_ZERO_DATE, ERROR_FOR_DIVISION_BY_ZERO, NO_ENGINE_SUBSTITUTION` |
| Strefa czasowa serwera | `SYSTEM`; Django: `USE_TZ = True`, `TIME_ZONE = "Europe/Warsaw"` |
| Uprawnienia konta aplikacji | `ALL` tylko na `farmer_db.*` i `test_farmer_db.*`, brak dostępu do innych baz |
| Migracje | wszystkie zastosowane (`core` 0001–0004), brak oczekujących |

Liczba rekordów w chwili audytu:

| Tabela | Rekordy |
|---|---|
| `auth_user` | 1 |
| `core_crop` | 4 |
| `core_field` | 2 |
| `core_cultivation` | 2 |
| `core_fieldwork` | 4 |
| `core_spraying` | 2 |
| `core_harvest` | 2 |
| `core_errorreport` | 0 |

Tryb `STRICT_TRANS_TABLES` jest włączony, więc MySQL odrzuca za długie teksty i niepoprawne
wartości zamiast je obcinać. MySQL 8.0.16+ egzekwuje ograniczenia `CHECK`, więc wersja 8.0.46
wymusza wszystkie ograniczenia zdefiniowane w modelach.

## 2. Modele i relacje

| Model (tabela) | Najważniejsze pola | Relacje (`on_delete`) |
|---|---|---|
| `User` (`auth_user`) | standardowy model Django | – |
| `Crop` (`core_crop`) | `name` (unikalna), `description` | wspólny słownik dla wszystkich użytkowników |
| `Field` (`core_field`) | `name`, `area_ha` Decimal(10,2), `soil_type`, `location_method`, `latitude`/`longitude` Decimal(9,6) | `owner` → User (`CASCADE`) |
| `Cultivation` (`core_cultivation`) | `season_year` (1980–2100), `status`, `sowing_date`, `planned_harvest_date` | `field` → Field (`CASCADE`), `crop` → Crop (`PROTECT`) |
| `FieldWork` (`core_fieldwork`) | `work_type`, `work_date`, `cost` Decimal(12,2) | `cultivation` → Cultivation (`CASCADE`) |
| `Spraying` (`core_spraying`) | `spraying_date`, `product_name`, `quantity` Decimal(10,2), `unit`, `cost` Decimal(12,2) | `cultivation` → Cultivation (`CASCADE`) |
| `Harvest` (`core_harvest`) | `harvest_date`, `quantity` Decimal(12,2), `unit`, `disposition`, `revenue`, `harvest_cost` Decimal(12,2) | `cultivation` → Cultivation (`CASCADE`) |
| `ErrorReport` (`core_errorreport`) | `category`, `description`, `status` | `user` → User (`CASCADE`) |

Łańcuch własności: `User → Field → Cultivation → FieldWork / Spraying / Harvest`.
Usunięcie użytkownika usuwa jego pola, uprawy, zdarzenia i zgłoszenia. Rodzaju uprawy
używanego w jakiejkolwiek uprawie nie da się usunąć (`PROTECT`).

Reguły `on_delete` realizuje ORM Django. W MySQL klucze obce mają `ON DELETE NO ACTION`,
co jest standardowym zachowaniem Django. Usunięcie rodzica bezpośrednio w SQL, z pominięciem
ORM, zostanie więc zablokowane przez bazę i nie powstaną rekordy osierocone.

Wszystkie pola dat zdarzeń są typu `DATE`. Pola `created_at`/`updated_at` są typu
`DATETIME(6)` i są zapisywane w UTC (`USE_TZ = True`).

## 3. Ograniczenia integralności

### 3.1. Wymuszane przez bazę MySQL

| Tabela | Ograniczenie | Reguła |
|---|---|---|
| `core_crop` | `name` (UNIQUE) | unikalna nazwa rodzaju uprawy |
| `core_field` | `core_field_unique_owner_name` (UNIQUE) | unikalna nazwa pola w obrębie właściciela |
| `core_field` | `core_field_area_ha_gt_zero` | `area_ha > 0` |
| `core_cultivation` | `core_cultivation_unique_field_crop_season` (UNIQUE) | jedna uprawa danego rodzaju na polu w sezonie |
| `core_cultivation` | `core_cultivation_chk_1` | `season_year >= 0` (z `PositiveSmallIntegerField`) |
| `core_fieldwork` | `core_fieldwork_cost_gte_zero` | `cost >= 0` |
| `core_spraying` | `core_spraying_quantity_gt_zero`, `core_spraying_cost_gte_zero` | `quantity > 0`, `cost >= 0` |
| `core_harvest` | `core_harvest_quantity_gt_zero`, `core_harvest_revenue_gte_zero`, `core_harvest_cost_gte_zero` | `quantity > 0`, `revenue >= 0`, `harvest_cost >= 0` |
| `core_harvest` | `core_harvest_unsold_revenue_zero` | `disposition = 'SOLD' OR revenue = 0` |
| wszystkie | klucze obce + `NOT NULL` | brak rekordów bez rodzica |

Indeksy: klucze główne, indeksy unikalne z tabeli powyżej oraz indeksy na każdym kluczu
obcym (`crop_id`, `cultivation_id`, `user_id`). Kolumna `core_field.owner_id` korzysta
z indeksu `(owner_id, name)`.

### 3.2. Wymuszane tylko przez aplikację (walidatory, `Model.clean()`, formularze)

- `season_year` w zakresie 1980–2100;
- `latitude` w zakresie −90…90, `longitude` w zakresie −180…180;
- wymagane pola zależne od `location_method` (adres, współrzędne, identyfikator działki);
- rok `sowing_date` równy `season_year`, `planned_harvest_date >= sowing_date`;
- rok daty pracy typu „Siew” równy sezonowi uprawy;
- wartości pól wyboru (`soil_type`, `status`, `work_type`, `unit`, `disposition`, `category`);
- nazwa pola unikalna bez względu na wielkość liter (`iexact`), unikalność e-maila
  użytkownika (`iexact`);
- uprawa i zdarzenia mogą wskazywać tylko pola i uprawy zalogowanego użytkownika.

## 4. Wyniki kontroli

### 4.1. Polecenia (MySQL, `.venv`, Python 3.14.7, Django 6.0.7)

| Polecenie | Wynik |
|---|---|
| `python manage.py check` | `System check identified no issues (0 silenced).` |
| `python manage.py check --database default` | brak problemów (w tym brak ostrzeżenia `mysql.W002` o trybie strict) |
| `python manage.py showmigrations` | wszystkie migracje `[X]`, `core` 0001–0004 |
| `python manage.py makemigrations --check --dry-run` | `No changes detected` |
| `python manage.py migrate --plan` | `No planned migration operations.` |
| `python manage.py test` | przed poprawką: `Ran 334 tests … OK`; po poprawce: `Ran 340 tests … OK` |
| `python -m pip check` | `No broken requirements found.` |
| `git diff --check` | brak błędów białych znaków |
| wyszukiwanie znaczników konfliktów | brak `<<<<<<<` / `=======` / `>>>>>>>` |

### 4.2. Zgodność modeli, migracji i schematu

- `makemigrations --check` nie wykrywa różnic między modelami a migracjami.
- Kolejność migracji jest liniowa: `0001_initial → 0002_harvest_disposition_and_more →
  0003_alter_cultivation_season_year → 0004_english_verbose_names`, bez rozgałęzień
  i scaleń. Migracje 0003 i 0004 zmieniają tylko walidatory i etykiety, bez zmian w SQL.
- Kolumny, typy (`decimal(p,s)`, `date`, `datetime(6)`, `smallint unsigned`), `NULL`,
  klucze obce, indeksy i ograniczenia `CHECK` odczytane z `information_schema` zgadzają się
  z modelami i z plikiem `docs/database/farmer_db_schema.sql`.

### 4.3. Integralność danych w `farmer_db`

Każda kontrola zwróciła **0** rekordów:

- rekordy osierocone: pola bez właściciela, uprawy bez pola lub rodzaju, prace, opryski
  i zbiory bez uprawy, zgłoszenia bez użytkownika;
- duplikaty: nazwa pola u właściciela (także po `LOWER(TRIM())`), nazwa rodzaju uprawy,
  uprawa (pole + rodzaj + sezon), nazwa użytkownika, niepusty e-mail;
- wartości spoza słowników dla wszystkich pól wyboru;
- `season_year` poza 1980–2100, rok siewu różny od sezonu, planowany zbiór przed siewem,
  praca „Siew” poza rokiem sezonu, zbiór przed siewem;
- przychód różny od 0 przy zbiorze niesprzedanym;
- współrzędne poza zakresem lub tylko jedna z dwóch współrzędnych;
- daty prac, oprysków i zbiorów oddalone o więcej niż rok od sezonu;
- puste nazwy pól, rodzajów upraw i środków.

### 4.4. Izolacja danych użytkowników

- Widoki pól, upraw, prac, oprysków, zbiorów, raportów i zgłoszeń filtrują zapytania po
  zalogowanym użytkowniku (`owner`, `field__owner`, `cultivation__field__owner`, `user`).
  Cudzy rekord daje 404.
- Listy wyboru w formularzach (pole w uprawie, uprawa w pracy, oprysku i zbiorze) zawierają
  tylko dane zalogowanego użytkownika, więc podstawienie cudzego ID kończy się błędem
  walidacji.
- Właściciel pola i autor zgłoszenia są ustawiani po stronie serwera, a status nowego
  zgłoszenia jest zawsze `NEW`.
- API JWT (`/api/...`) udostępnia tylko dane bieżącego użytkownika.
- Rodzaje upraw (`Crop`) są celowo wspólne dla wszystkich użytkowników.

Izolację pokrywają istniejące testy (`test_fields`, `test_cultivations`, `test_fieldworks`,
`test_sprayings`, `test_harvests`, `test_reports`, `test_error_reports`, `test_final_integration`).

### 4.5. Konfiguracja

- `DATABASES` ma tylko silnik `django.db.backends.mysql`, bez SQLite ani innego silnika
  zapasowego. `DB_NAME`, `DB_USER` i `DB_PASSWORD` są wymagane, a ich brak kończy się
  `ImproperlyConfigured`.
- W repozytorium nie ma odwołań do SQLite ani PostgreSQL poza testem
  `test_db_engine_cannot_switch_to_sqlite`, który sprawdza, że silnika nie da się zmienić.
- Testy używają bazy `test_farmer_db` (`utf8mb4` / `utf8mb4_unicode_ci`) na tym samym serwerze.

## 5. Znalezione problemy

### 5.1. Naprawione w tym audycie (bez zmiany schematu)

**P1. Konflikt unikalności wykryty dopiero przez bazę kończył się błędem HTTP 500.**
Formularze sprawdzają duplikaty przed zapisem, ale dwa równoległe żądania z tymi samymi
danymi (np. podwójne kliknięcie „Zapisz”) mogą oba przejść walidację. Drugi zapis trafiał
wtedy na indeks unikalny MySQL (`IntegrityError 1062 Duplicate entry`) i użytkownik
dostawał stronę błędu 500. Dotyczyło to dodawania i edycji pola, dodawania i edycji uprawy
oraz dodawania rodzaju uprawy.

Poprawka: `UniqueConflictMixin` w `core/views.py`. Zapis odbywa się w `transaction.atomic()`.
Przy `IntegrityError` widok ponownie sprawdza ograniczenia unikalności modelu. Jeśli to
duplikat, formularz wraca z dotychczasowym komunikatem („Masz już pole o tej nazwie.”,
„Taka uprawa jest już przypisana do tego pola i sezonu.”, „Rodzaj uprawy o tej nazwie już
istnieje.”) i bez komunikatu o sukcesie. Każdy inny `IntegrityError` jest przekazywany dalej.
Komunikaty o sukcesie i ich tłumaczenia zostały bez zmian.

Test regresyjny: `core/tests/test_unique_conflicts.py` (6 testów; przed poprawką 4 z nich
kończyły się `IntegrityError`).

### 5.2. Wymagające zmiany modelu lub migracji (tylko opis, czekają na decyzję)

| # | Problem | Ryzyko | Proponowana zmiana |
|---|---|---|---|
| P2 | Zakres `season_year` 1980–2100 jest wymuszany tylko w aplikacji, a baza sprawdza jedynie `>= 0`. | niskie | `CheckConstraint(season_year__gte=1980, season_year__lte=2100)` |
| P3 | Wartości pól wyboru nie są sprawdzane przez bazę. Zapis z pominięciem formularzy (shell, skrypt, admin z własnym kodem) może zapisać dowolny tekst. | niskie | `CheckConstraint(<pole>__in=<choices>)` dla każdego pola wyboru |
| P4 | Zakres współrzędnych i reguła „obie współrzędne albo żadna” są tylko w aplikacji. | niskie | `CheckConstraint` na zakres oraz na `latitude IS NULL = longitude IS NULL` |
| P5 | `planned_harvest_date >= sowing_date` i rok siewu równy sezonowi są tylko w `Model.clean()` i formularzu. | niskie | `CheckConstraint` z `Q(...)` i `ExtractYear` |
| P6 | E-mail użytkownika jest unikalny tylko w formularzu, `auth_user.email` nie ma indeksu unikalnego. Dwie równoległe rejestracje mogą utworzyć ten sam e-mail. Logowanie odbywa się po nazwie użytkownika, więc nie blokuje to działania. | niskie | wymaga własnego modelu użytkownika lub osobnej migracji na tabeli `auth_user`, decyzja projektowa |
| P7 | Porównywanie `utf8mb4_unicode_ci` ignoruje wielkość liter i część znaków diakrytycznych. Sprawdzone zapytaniem: `'Żyto' = 'Zyto'` → 1, `'Łubin' = 'Lubin'` → 0. Indeks unikalny uzna więc „Zyto” i „Żyto” za tę samą nazwę. Aplikacja pokazuje wtedy poprawny komunikat walidacji, bez błędu 500, ale komentarz w `CropForm.clean_name` zakłada rozróżnianie polskich liter. | informacyjne | zmiana porównywania kolumn `name` (np. `utf8mb4_0900_as_ci`) wymaga migracji, do decyzji |
| P8 | Brak indeksów na datach zdarzeń (`work_date`, `spraying_date`, `harvest_date`) i na `season_year`, które służą do sortowania i filtrowania list. Przy obecnej skali danych nie ma to znaczenia. | wydajność, przy dużej liczbie rekordów | indeksy złożone `(cultivation_id, <data>)` w `Meta.indexes` |

### 5.3. Uwagi bez potrzeby zmian

- Daty oprysków i zbiorów nie są wiązane z rokiem sezonu, celowo, bo zbiór może przypaść
  na kolejny rok. Obecne dane mieszczą się w zakresie sezon ± 1 rok.
- Kod nie używa wyszukiwań po części daty na polach `DateTimeField` (`__date`, `__year`,
  `Trunc`), więc tabele stref czasowych MySQL nie są potrzebne. Konto aplikacji nie ma do
  nich dostępu. Gdyby takie zapytania doszły w przyszłości, administrator musi załadować
  strefy czasowe do MySQL.

## 6. Polecenie `seed_demo_data`

Polecenie jest zgodne z aktualnymi modelami. Używa istniejących pól, w tym `disposition`,
podaje wartości spełniające wszystkie ograniczenia i działa w jednej transakcji
(`@transaction.atomic`). Test `test_seed_demo_data` przechodzi. Braki do uwzględnienia
w osobnym zadaniu przebudowy (na tym etapie polecenie nie było zmieniane):

1. Nie tworzy danych dla modelu `ErrorReport`.
2. Pokrywa tylko część wartości słownikowych: status `ACTIVE` (brak `PLANNED`, `COMPLETED`),
   przeznaczenie `SOLD` (brak `STORED`, `DISCARDED`, więc ograniczenie
   `core_harvest_unsold_revenue_zero` nie jest pokazane w danych), gleby `LOAMY` i `SANDY`,
   lokalizacje `GPS` i `ADDRESS` (brak `MAP`, `PARCEL`), prace `PLOWING` i `SOWING`.
3. Nie wywołuje `full_clean()`, więc dane omijają walidatory modelu. Obecne wartości są
   poprawne, ale przyszłe zmiany danych demonstracyjnych nie będą sprawdzane.
4. `Field.objects.update_or_create(owner=user, name="Pole Północne")` nadpisuje istniejące
   pole użytkownika o tej nazwie (także różniącej się wielkością liter, przez porównywanie
   `_ci`). Uruchomienie na koncie z prawdziwymi danymi może zmienić prawdziwe pole.
5. `update_or_create` dla prac, oprysków i zbiorów szuka po polach, które nie są unikalne.
   Jeśli użytkownik ma dwa pasujące rekordy, polecenie kończy się `MultipleObjectsReturned`.
   Może też nadpisać rekord wpisany ręcznie.
6. Liczby w podsumowaniu są wpisane na stałe (np. „2”), zamiast liczyć faktycznie
   utworzone lub zaktualizowane rekordy.
7. Daty są na stałe ustawione na sezon 2026.

**Aktualizacja (gałąź `feature/seed-demo-data`):** wszystkie powyższe braki zostały usunięte. Polecenie obejmuje teraz `ErrorReport` i wszystkie wartości słownikowe, wywołuje `full_clean()`, nie używa `update_or_create`, nie nadpisuje istniejących rekordów, ma opcję `--dry-run` i wypisuje faktyczne liczniki. Opis znajduje się w README i w `docs/dokumentacja_bazy_danych.md`.

## 7. Wniosek

**Baza MySQL `farmer_db` jest gotowa do normalnego używania przez aplikację.**

Schemat zgadza się z modelami i migracjami, wszystkie migracje są zastosowane, nie ma
oczekujących zmian, a dane nie mają rekordów osieroconych, duplikatów ani wartości
niepoprawnych. Izolacja danych użytkowników działa w widokach, formularzach i API.
Konfiguracja korzysta wyłącznie z MySQL w trybie strict z `utf8mb4`. Jedyny problem, który
mógł wpływać na użytkownika (błąd 500 przy równoległym zapisie duplikatu), został naprawiony
i ma test regresyjny.

Problemy P2–P8 nie blokują używania bazy. Dotyczą wzmocnienia ograniczeń po stronie MySQL
i wydajności przy większej liczbie danych. Wymagają nowej migracji, więc czekają na decyzję.
Przebudowa `seed_demo_data` (sekcja 6) jest osobnym zadaniem.
