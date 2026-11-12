# Hosting – Farmer App

Data rozeznania: 2026-11-12. Cel: bezpłatnie wystawić aplikację (Django 6 + MySQL) w Internecie,
żeby można ją było pokazać i testować. Ceny i limity darmowych planów często się zmieniają,
dlatego przed rejestracją warto je sprawdzić na stronach dostawców.

## 1. Wymagania aplikacji

- Python 3.14, Django 6.0, serwer WSGI (Gunicorn);
- baza MySQL 8 (projekt jest przygotowany tylko pod MySQL);
- HTTPS (cookie `Secure`, HSTS, przekierowanie na HTTPS);
- pliki statyczne (CSS, JS, ikony) i załączniki do zgłoszeń błędów (`media/`).

## 2. Porównanie darmowych opcji

| Dostawca | Co daje za darmo | MySQL za darmo | Ograniczenia | Ocena |
|---|---|---|---|---|
| **Render** (aplikacja) | web service z Dockerem, HTTPS, adres `*.onrender.com`, wdrażanie z GitHuba | nie (tylko PostgreSQL na 30 dni) | usypia po 15 min bez ruchu, start ok. 1 min; 750 h/mies.; dysk ulotny | **wybrany do aplikacji** |
| **TiDB Cloud Starter** (baza) | baza zgodna z MySQL 8, do 5 GiB danych na instancję, TLS | tak (zgodna z MySQL) | po przekroczeniu limitu zapytań baza zwalnia; potrzebny dialekt `django-tidb` | **wybrany do bazy** |
| PythonAnywhere | 1 aplikacja, 512 MiB dysku | **nie dla nowych kont** (od 2026-01-15 MySQL tylko w planie płatnym od 10 USD/mies.) | aplikacja wygasa po miesiącu bez przedłużenia | odrzucony |
| Aiven | darmowe PostgreSQL, Valkey, Kafka | **nie** (MySQL tylko w płatnym planie Developer) | — | odrzucony |
| Railway | 30 dni próbnie, potem 1 USD kredytu/mies. | szablon MySQL, ale płatny po wykorzystaniu kredytu | rozliczanie za zużycie | odrzucony |
| Filess.io | MySQL | tak | tylko 10 MB danych | za mało miejsca |
| Oracle Cloud Always Free | VM i MySQL HeatWave | tak | wymaga karty płatniczej i ręcznej konfiguracji serwera | możliwy później |

**Decyzja:** aplikacja na **Render** (plan Free, Docker) + baza **TiDB Cloud Starter**
(darmowa, zgodna z MySQL). Oba serwisy nie wymagają karty płatniczej, mają szyfrowane
połączenia i wdrażają się z repozytorium GitHub.

Gdy projekt będzie potrzebował stałej dostępności (bez usypiania), najprostsze płatne przejście to
Render Starter (ok. 7 USD/mies.) albo PythonAnywhere Developer (10 USD/mies., z MySQL).

## 3. Co zostało przygotowane w repozytorium

| Plik | Rola |
|---|---|
| `Dockerfile` | obraz Python 3.14 z biblioteką klienta MySQL, `collectstatic` w czasie budowania, użytkownik bez uprawnień root |
| `docker-entrypoint.sh` | przy starcie: `migrate`, opcjonalnie pierwszy administrator i dane demo, potem Gunicorn |
| `render.yaml` | Blueprint Render: darmowy web service, region Frankfurt, zmienne środowiskowe |
| `.dockerignore` | do obrazu nie trafiają `.env`, `.venv`, `.git`, `media/` |
| `config/settings.py` | WhiteNoise dla plików statycznych, `DB_ENGINE=tidb`, TLS do bazy (`DB_SSL_CA`), automatyczny host Render, opcjonalne `SECURE_PROXY_SSL_HEADER` |
| `core/tests/test_deployment_settings.py` | testy powyższych ustawień |

Nowe zmienne środowiskowe:

| Zmienna | Znaczenie |
|---|---|
| `DB_ENGINE=tidb` | używa dialektu `django_tidb`; każda inna wartość (albo brak) = zwykły MySQL |
| `DB_SSL_CA` | ścieżka do certyfikatów CA; włącza szyfrowanie i weryfikację serwera bazy (`VERIFY_IDENTITY`) |
| `DJANGO_TRUST_X_FORWARDED_PROTO=True` | ufa nagłówkowi `X-Forwarded-Proto` od proxy Render (bez tego przekierowanie na HTTPS by się zapętliło) |
| `RENDER_EXTERNAL_HOSTNAME` | ustawia ją sam Render; host jest dopisywany do `ALLOWED_HOSTS` i `CSRF_TRUSTED_ORIGINS` |
| `DJANGO_SUPERUSER_USERNAME`, `DJANGO_SUPERUSER_PASSWORD`, `DJANGO_SUPERUSER_EMAIL` | pierwszy administrator tworzony przy starcie (plan Free nie ma konsoli) |
| `SEED_DEMO_DATA_FOR` | nazwa użytkownika, który dostaje dane demonstracyjne (polecenie dodaje tylko brakujące rekordy) |

## 4. Wdrożenie krok po kroku

### 4.1. Baza w TiDB Cloud

1. Załóż konto na <https://tidbcloud.com> (logowanie przez GitHub lub Google).
2. Utwórz instancję **Starter**, region AWS **Frankfurt (eu-central-1)** – blisko serwera Render.
3. W oknie **Connect** wygeneruj hasło i zanotuj: *Host*, *Port* (4000), *User*
   (w postaci `xxxxxxxx.root`), *Password*.
4. W **SQL Editor** wykonaj:

   ```sql
   CREATE DATABASE farmer_db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
   ```

### 4.2. Aplikacja w Render

1. Kod musi być na gałęzi `main` w repozytorium GitHub.
2. Załóż konto na <https://render.com> (logowanie przez GitHub).
3. **New → Blueprint**, wybierz repozytorium. Render odczyta `render.yaml`.
4. Uzupełnij wartości oznaczone w Blueprincie jako `sync: false`:
   - `DB_HOST`, `DB_USER`, `DB_PASSWORD` – z TiDB Cloud;
   - `DJANGO_SUPERUSER_USERNAME`, `DJANGO_SUPERUSER_PASSWORD` (silne hasło),
     `DJANGO_SUPERUSER_EMAIL`;
   - `SEED_DEMO_DATA_FOR` – np. ta sama nazwa co administrator, albo puste pole.
5. **Apply**. Pierwsze budowanie obrazu trwa kilka minut. W logach powinny być widoczne
   migracje, utworzenie administratora i start Gunicorna.
6. Aplikacja działa pod adresem `https://farmer-app.onrender.com` (albo z dopiskiem,
   jeśli nazwa jest zajęta). Panel administracyjny: `/admin/`.
7. Po pierwszym udanym starcie można usunąć `DJANGO_SUPERUSER_PASSWORD` ze zmiennych
   (konto już istnieje).

Każdy kolejny `push` (merge PR) do `main` automatycznie buduje i wdraża nową wersję.

### 4.3. Sprawdzenie po wdrożeniu

- strona logowania otwiera się przez HTTPS, a `http://` przekierowuje na `https://`;
- logowanie, dodanie pola i uprawy działa;
- w narzędziach przeglądarki brak błędów CSP, pliki CSS mają nazwy z hashem;
- `/admin/` pozwala zalogować się kontem administratora;
- nagłówki: `Strict-Transport-Security`, `Content-Security-Policy`, `X-Frame-Options: DENY`.

## 5. Ograniczenia darmowej konfiguracji

- **Usypianie:** po 15 minutach bez ruchu Render zatrzymuje aplikację, pierwsze wejście
  trwa wtedy około minuty. Przed prezentacją warto otworzyć stronę wcześniej.
- **Załączniki do zgłoszeń błędów:** dysk w planie Free jest ulotny. Pliki w `media/` znikają
  przy każdym wdrożeniu, restarcie i uśpieniu. Same zgłoszenia (w bazie) zostają.
  Trwałe przechowywanie wymaga płatnego dysku Render albo zewnętrznego magazynu plików (np. S3).
- **Liczniki blokady logowania** są w pamięci jednego procesu (jeden worker Gunicorna
  z 4 wątkami). Restart lub uśpienie je zeruje.
- **Kopie zapasowe:** darmowy plan TiDB nie daje gwarancji kopii. Ważne dane eksportuj
  (np. `mysqldump` albo MySQL Workbench → *Data Export*, połączenie z TLS).
- **HSTS** jest ustawione na 1 godzinę (`DJANGO_SECURE_HSTS_SECONDS=3600`). Na domenie
  `onrender.com` nie włączamy `includeSubDomains` ani `preload`, bo nie kontrolujemy tej domeny.

## 6. Połączenie MySQL Workbench z bazą TiDB

*Database → Manage Connections → New*: Hostname i Port z TiDB Cloud, Username jak wyżej.
W zakładce **SSL** ustaw *Use SSL: Require*. Workbench może pokazać ostrzeżenie o nieznanej
wersji serwera, które można zignorować.
