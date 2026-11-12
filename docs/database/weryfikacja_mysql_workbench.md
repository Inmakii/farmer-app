# Weryfikacja materiałów MySQL Workbench – Farmer App

Data weryfikacji: 2026-11-04 (kontrola początkowa i ponowna kontrola po ręcznej korekcie w MySQL Workbench)
Gałąź: `docs/mysql-workbench-model`

## 1. Cel

Sprawdzenie, czy materiały bazy danych (model MySQL Workbench, diagram ERD, eksport SQL
i opisy w dokumentacji) odpowiadają aktualnej strukturze bazy `farmer_db`, modelom Django
i migracjom aplikacji `core`.

## 2. Środowisko

| Parametr | Wartość |
|---|---|
| Serwer | MySQL 8.0.46 |
| Silnik Django | `django.db.backends.mysql` |
| Baza | `farmer_db`, `utf8mb4` / `utf8mb4_unicode_ci`, InnoDB |
| Migracje `core` | `0001_initial`, `0002_harvest_disposition_and_more`, `0003_alter_cultivation_season_year`, `0004_english_verbose_names` – wszystkie zastosowane |
| Obiekty bazy | 17 tabel; brak widoków, procedur, funkcji i wyzwalaczy |

Struktura `farmer_db` była odczytywana wyłącznie zapytaniami do `information_schema`
i poleceniem `SHOW CREATE TABLE`. Dane w bazie nie były zmieniane.

## 3. Sprawdzone artefakty

| Artefakt | Wynik |
|---|---|
| `core/models.py` i migracje `core` | zgodne z bazą (`makemigrations --check`: brak zmian) |
| `docs/database/farmer_db_schema.sql` | **był nieaktualny**, wygenerowany ponownie (sekcja 5) |
| `docs/diagrams/farmer_db_model.mwb` | brakowało jednej kolumny; poprawiony w MySQL Workbench, obecnie zgodny (sekcja 6) |
| `docs/diagrams/erd_farmer_app.png` | brakowało tej samej kolumny; wyeksportowany ponownie, obecnie zgodny (sekcja 6) |
| `docs/dokumentacja_bazy_danych.md` | opisy tabel zgodne; doprecyzowano wartości domyślne i dodano odwołanie do tego raportu |
| `docs/stan_uzywalnosci_bazy.md` | poprawiono błędne stwierdzenie o zgodności eksportu SQL |
| `README.md` | dodano link do tego raportu |

## 4. Tabele domenowe i relacje

Tabele: `auth_user`, `core_crop`, `core_field`, `core_cultivation`, `core_fieldwork`,
`core_spraying`, `core_harvest`, `core_errorreport`.

| Relacja | Klucz obcy | `on_delete` (Django) | Reguła w MySQL |
|---|---|---|---|
| użytkownik → pola | `core_field.owner_id` → `auth_user.id` | `CASCADE` | `NO ACTION` |
| użytkownik → zgłoszenia błędów | `core_errorreport.user_id` → `auth_user.id` | `CASCADE` | `NO ACTION` |
| pole → uprawy | `core_cultivation.field_id` → `core_field.id` | `CASCADE` | `NO ACTION` |
| rodzaj uprawy → uprawy | `core_cultivation.crop_id` → `core_crop.id` | `PROTECT` | `NO ACTION` |
| uprawa → prace | `core_fieldwork.cultivation_id` → `core_cultivation.id` | `CASCADE` | `NO ACTION` |
| uprawa → opryski | `core_spraying.cultivation_id` → `core_cultivation.id` | `CASCADE` | `NO ACTION` |
| uprawa → zbiory | `core_harvest.cultivation_id` → `core_cultivation.id` | `CASCADE` | `NO ACTION` |

Reguły `on_delete` realizuje ORM Django. W MySQL klucze obce mają domyślne `NO ACTION`,
co jest standardowym zachowaniem Django. Innych relacji między tabelami domenowymi nie ma.

Ograniczenia w tabelach domenowych:

- klucze główne `id` (BIGINT, a w `auth_user` INT, auto increment);
- UNIQUE: `core_crop.name`, `core_field (owner_id, name)`, `core_cultivation (field_id, crop_id, season_year)`, `auth_user.username`;
- CHECK: `core_field_area_ha_gt_zero`, `core_cultivation_chk_1` (`season_year >= 0`),
  `core_fieldwork_cost_gte_zero`, `core_spraying_quantity_gt_zero`, `core_spraying_cost_gte_zero`,
  `core_harvest_quantity_gt_zero`, `core_harvest_revenue_gte_zero`, `core_harvest_cost_gte_zero`,
  `core_harvest_unsold_revenue_zero` (oraz `django_admin_log_chk_1` poza domeną);
- indeksy: na każdym kluczu obcym, przy czym `core_field.owner_id` korzysta z indeksu
  `(owner_id, name)`.

## 5. Eksport SQL

### 5.1. Znalezione rozbieżności w poprzednim pliku

Poprzedni eksport pochodził z 18.08.2026, sprzed migracji 0002. Kolumnę `disposition`
i ograniczenie `core_harvest_unsold_revenue_zero` dopisano do niego później ręcznie:

- `core_harvest.disposition` miał `DEFAULT 'SOLD'` i stał w innym miejscu tabeli. W bazie
  kolumna nie ma klauzuli `DEFAULT`, bo Django usuwa tymczasową wartość domyślną po
  `AddField`, i jest ostatnią kolumną tabeli;
- plik zaczynał się od `CREATE DATABASE IF NOT EXISTS farmer_db; USE farmer_db;`
  i zawierał `DROP TABLE IF EXISTS` dla każdej tabeli. Import usunąłby więc tabele
  prawdziwej bazy `farmer_db` razem z danymi;
- zawierał liczniki `AUTO_INCREMENT=N` zależne od lokalnych rekordów.

### 5.2. Nowy eksport

Plik wygenerowano poleceniem `mysqldump` 8.0.46 z opcjami `--no-data`,
`--skip-add-drop-table`, `--single-transaction`, `--no-tablespaces`, `--set-gtid-purged=OFF`,
`--skip-comments`, `--routines`, `--triggers`, `--events` i `--default-character-set=utf8mb4`.
Liczniki `AUTO_INCREMENT=N` zostały usunięte. Plik:

- zawiera wyłącznie strukturę 17 tabel Django i aplikacji: kolumny, klucze główne i obce,
  indeksy, UNIQUE, CHECK, `utf8mb4` / `utf8mb4_unicode_ci`;
- **nie zawiera danych**: brak `INSERT`, rekordów użytkowników, hashy haseł, sesji, tokenów
  i danych gospodarstw. Tabela `auth_user` ma tylko definicję kolumny `password`, bez wartości;
- nie zawiera danych połączenia ani `DEFINER`;
- nie tworzy, nie wybiera i nie usuwa żadnej bazy ani tabeli.

Kontrola importu: plik zaimportowano do nowej, pustej bazy tymczasowej (`test_farmer_db`,
tej samej, której Django używa w testach; po kontroli została usunięta). Struktura po imporcie
jest identyczna z `farmer_db` według `information_schema`: 17 tabel, 103 kolumny (typ, `NULL`,
`DEFAULT`, charset, collation), 46 pozycji indeksów, 16 kluczy obcych z regułami, 10 ograniczeń
CHECK. `SHOW CREATE TABLE` różni się tylko formą zapisu: po imporcie MySQL dopisuje jawne
`CHARACTER SET utf8mb4` przed `COLLATE`.

### 5.3. Bezpieczne odtworzenie schematu z eksportu

Eksport służy do przeglądu struktury, importu w Workbench i porównań. **Nie importuj go do
`farmer_db`.** Bazę dla aplikacji tworzy się poleceniem `python manage.py migrate` na pustej
bazie. Import eksportu nie wypełnia tabeli `django_migrations`, więc Django próbowałoby
utworzyć istniejące tabele.

Odtworzenie w osobnej, pustej bazie (przykładowa nazwa `farmer_schema_check`):

1. Utwórz pustą bazę jako administrator MySQL:
   ```sql
   CREATE DATABASE farmer_schema_check CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
   ```
2. Zaimportuj plik z wiersza poleceń (PowerShell nie obsługuje przekierowania `<`,
   dlatego wywołanie idzie przez `cmd`):
   ```powershell
   cmd /c "mysql --default-character-set=utf8mb4 -u <użytkownik> -p farmer_schema_check < docs\database\farmer_db_schema.sql"
   ```
   albo w MySQL Workbench: **Server → Data Import → Import from Self-Contained File**,
   wskaż `docs/database/farmer_db_schema.sql`, w polu **Default Target Schema** wybierz
   `farmer_schema_check`, kliknij **Start Import**.
3. Po sprawdzeniu usuń bazę pomocniczą: `DROP DATABASE farmer_schema_check;`. Upewnij się,
   że nazwa nie jest `farmer_db`.

## 6. Model `.mwb` i diagram PNG

### 6.1. Wynik kontroli `farmer_db_model.mwb`

**Kontrola początkowa.** Model pochodził z 18.08.2026, sprzed migracji 0002. W tabeli
`core_harvest` brakowało kolumny `disposition` (VARCHAR(10), NOT NULL). Pozostałe tabele,
kolumny, indeksy i klucze obce były zgodne z bazą.

**Korekta.** Brakującą kolumnę dodano ręcznie w MySQL Workbench według procedury z sekcji 6.3,
a model zapisano. Problem jest naprawiony.

**Ponowna kontrola po korekcie.** Wykonano ją na kopii pliku poza repozytorium. Kopia była
identyczna z plikiem w repozytorium (SHA-256), a pliki tymczasowe zostały usunięte po kontroli.

- Plik jest poprawnym archiwum ZIP (test CRC bez błędów) z `document.mwb.xml`
  (`document_type="MySQL Workbench Model"`, `grt_format="2.0"`), `@db/data.db` i `lock`.
  Wpis `lock` oznacza zwykle zapis przy otwartym modelu i nie wpływa na jego otwieranie.
- Schemat `farmer_db` w modelu (`utf8mb4` / `utf8mb4_unicode_ci`) zawiera te same 17 tabel
  co baza. Wszystkie 103 kolumny zgadzają się co do nazwy, kolejności, typu, długości,
  precyzji, `NOT NULL`, `UNSIGNED`, auto increment i wartości domyślnej. Zgodne są też
  klucze główne, indeksy UNIQUE i zwykłe oraz wszystkie 16 kluczy obcych (kolumny i tabele
  docelowe). Kontrola nie wykazała żadnej rozbieżności.
- Kolumna `core_harvest.disposition` jest ostatnią kolumną tabeli, po `cultivation_id`, tak jak
  w bazie: `VARCHAR(10)`, `NOT NULL`, bez wartości domyślnej, bez PK, UQ i AI. Ma porównywanie
  „Table Default”, czyli dziedziczy `utf8mb4_unicode_ci` z tabeli. Pozostałe kolumny tekstowe
  mają tę samą wartość wpisaną jawnie, więc efektywne porównywanie jest identyczne.
- Model ma dwa diagramy: **EER Diagram** (wszystkie 17 tabel, 16 połączeń) oraz
  **EER Diagram1** (8 tabel domenowych, 7 połączeń z sekcji 4).
- Model zawiera dodatkowo pusty schemat `mydb`, domyślny schemat nowego modelu Workbench.
  Nie ma w nim tabel i nie wpływa na zgodność.
- Przy zapisie MySQL Workbench utworzył kopię zapasową `docs/diagrams/farmer_db_model.mwb.bak`
  (poprzednia wersja modelu). Plik jest ignorowany przez Git (`*.mwb.bak` w `.gitignore`)
  i nie jest częścią materiałów projektu. Można go usunąć lokalnie.

Model nie zawiera ograniczeń CHECK. Edytor modelu MySQL Workbench 8.0 ich nie przechowuje,
więc ich brak nie jest błędem pliku. CHECK są w eksporcie SQL i w migracjach.

### 6.2. Wynik kontroli `erd_farmer_app.png`

**Kontrola początkowa.** Obraz (1838 × 989) przedstawiał 8 tabel domenowych i 7 relacji,
ale bez kolumny `core_harvest.disposition`.

**Po korekcie.** Obraz wyeksportowano ponownie z diagramu **EER Diagram1** (1838 × 1012).
Przedstawia tabele `auth_user`, `core_field`, `core_errorreport`, `core_crop`,
`core_cultivation`, `core_fieldwork`, `core_spraying` i `core_harvest` oraz 7 relacji 1:N
z sekcji 4. Tabela `core_harvest` pokazuje kolumnę `disposition VARCHAR(10)` jako ostatnią,
po `cultivation_id`. Typy kolumn i klucze są zgodne z bazą.

### 6.3. Procedura aktualizacji w MySQL Workbench

Pliku `.mwb` nie da się bezpiecznie zaktualizować bez GUI, a ręczna edycja XML w archiwum
jest niedozwolona. Poniższe kroki (MySQL Workbench 8.0) wykonano ręcznie 2026-11-04, aby
dodać `core_harvest.disposition`. Ta sama procedura służy do przyszłych aktualizacji
modelu po zmianach w migracjach.

1. Uruchom MySQL Workbench i wybierz **File → Open Model…**, a następnie
   `docs/diagrams/farmer_db_model.mwb`. Jeśli pojawi się pytanie o plik blokady (`lock`),
   wybierz otwarcie modelu.
2. W zakładce **MySQL Model**, w sekcji **Physical Schemas**, otwórz kartę `farmer_db`
   i kliknij dwukrotnie zmienianą tabelę (tu: `core_harvest`).
3. W edytorze tabeli, na karcie **Columns**, dodaj lub zmień kolumnę zgodnie z bazą
   (tu: pusty wiersz pod `cultivation_id`):
   - **Column Name:** `disposition`
   - **Datatype:** `VARCHAR(10)`
   - zaznacz **NN** (Not Null), pozostaw odznaczone PK, UQ, AI;
   - **Default/Expression:** puste;
   - w szczegółach kolumny **Collation:** `utf8mb4_unicode_ci` (albo „Table Default”).
4. Zamknij edytor tabeli. Otwórz diagram **EER Diagram1** i sprawdź, czy figura
   `core_harvest` pokazuje nową kolumnę. Jeśli figura ma stałą wysokość, przeciągnij jej
   dolną krawędź. To samo sprawdź na diagramie **EER Diagram**.
5. Opcjonalnie usuń pusty schemat `mydb`: prawy przycisk na karcie `mydb` → **Delete Schema**.
6. Zapisz model: **File → Save Model** (Ctrl+S), nadpisując `docs/diagrams/farmer_db_model.mwb`.
7. Mając aktywny diagram **EER Diagram1**, wybierz **File → Export → Export as PNG…**
   i nadpisz `docs/diagrams/erd_farmer_app.png`.
8. Nie używaj **Database → Forward Engineer** ani **Database → Synchronize Model** wobec
   `farmer_db`. Te funkcje mogą zmienić prawdziwą bazę. Strukturę bazy zmieniają wyłącznie
   migracje Django.

Po zapisaniu sprawdź model ponownie, porównując `document.mwb.xml` z kopii pliku
z `information_schema` bazy `farmer_db`, tak jak w sekcji 6.1.

## 7. Podsumowanie

| Artefakt | Zgodny z aktualną bazą |
|---|---|
| modele Django i migracje 0001–0004 | tak |
| `farmer_db_schema.sql` | tak, po ponownym wygenerowaniu w tej weryfikacji |
| `farmer_db_model.mwb` | tak, po ręcznym dodaniu `core_harvest.disposition` w MySQL Workbench |
| `erd_farmer_app.png` | tak, po ponownym eksporcie z diagramu **EER Diagram1** |
| opisy w dokumentacji | tak, po doprecyzowaniu |

Wszystkie materiały bazy danych (`.mwb`, PNG i eksport SQL) są zgodne z aktualną strukturą
`farmer_db`, modelami Django i migracjami `core` 0001–0004.

## 8. Aktualizacja po migracji 0005 (2026-11-12)

Migracja `0005_error_report_page_and_attachments` zmieniła strukturę bazy:

- `core_errorreport`: nowa kolumna `page VARCHAR(500) NOT NULL` (po `description`);
- nowa tabela `core_errorreportattachment` (`id`, `file`, `original_name`, `content_type`,
  `size INT UNSIGNED` z `CHECK (size >= 0)`, `created_at`, `report_id`) z kluczem obcym
  `report_id` → `core_errorreport.id`.

| Artefakt | Stan |
|---|---|
| `farmer_db_schema.sql` | zaktualizowany: wygenerowany ponownie (`mysqldump` 8.4.9, `--no-data`); różnica względem poprzedniej wersji to wyłącznie powyższe zmiany |
| `dokumentacja_bazy_danych.md` | zaktualizowana (sekcje 4.8, 4.9, 5, 10) |
| `farmer_db_model.mwb` | zaktualizowany w MySQL Workbench 8.0.47: kolumna `page` i tabela `core_errorreportattachment` z kluczem obcym `report_id` → `core_errorreport.id` (`NO ACTION`) na diagramie **EER Diagram1** |
| `erd_farmer_app.png` | wyeksportowany ponownie z **EER Diagram1** |

Weryfikacja po aktualizacji: kolumny wszystkich tabel `core_*` i `auth_user` z
`document.mwb.xml` porównano z `information_schema.columns` bazy `farmer_db`
(nazwa, typ, `NOT NULL`, `UNSIGNED`). Porównano 78 kolumn, bez różnic. Model, PNG i eksport SQL
są zgodne z migracjami `core` 0001–0005.

Uwaga: nowy MySQL Workbench 26.x nie obsługuje modelowania ani plików `.mwb`. Model edytuje się
w MySQL Workbench 8.0 (archiwum: <https://downloads.mysql.com/archives/workbench/>).

Wykonane kroki w MySQL Workbench (tylko model, bez zmian w bazie):

1. Otwórz `docs/diagrams/farmer_db_model.mwb`.
2. W tabeli `core_errorreport` dodaj kolumnę `page`, typ `VARCHAR(500)`, *NN*.
3. Dodaj tabelę `core_errorreportattachment` z kolumnami jak w `farmer_db_schema.sql`
   (najprościej: **File → Import → Reverse Engineer MySQL Create Script**, zaimportować
   eksport SQL do nowego modelu i skopiować tabelę) i połącz ją relacją 1:N z
   `core_errorreport` (**Place a Relationship Using Existing Columns**, `report_id` → `id`).
4. Zapisz model, wyeksportuj diagram: **File → Export → Export as PNG** do
   `docs/diagrams/erd_farmer_app.png`.
5. Tak jak wcześniej: nie używaj **Forward Engineer** ani **Synchronize Model** wobec `farmer_db`.

