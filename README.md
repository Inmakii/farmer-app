# Farmer App

Farmer App to studencka aplikacja internetowa dla właścicieli i osób zarządzających gospodarstwami rolnymi. Pozwala prowadzić ewidencję pól i sezonowych upraw, zapisywać wykonane zabiegi oraz zbiory, a następnie obliczać koszty, przychody i wynik finansowy. Administrator obsługuje słownik upraw i statusy zgłoszeń przez panel Django Admin.

## Funkcje

- rejestracja, logowanie i bezpieczne wylogowanie przez POST;
- profil użytkownika, edycja danych i zmiana hasła z zachowaniem sesji;
- CRUD własnych pól, upraw sezonowych, prac, oprysków i zbiorów;
- wyszukiwanie, filtry oraz paginacja list;
- raport gospodarstwa, pola i uprawy z kosztami, przychodami i zyskiem;
- zgłaszanie błędów i podgląd własnych zgłoszeń;
- administracja rodzajami upraw i statusami zgłoszeń;
- idempotentna komenda przygotowująca dane demonstracyjne;
- izolacja danych każdego właściciela oraz testy bezpieczeństwa.

## Technologie

- Python 3.14.6;
- Django 6.0.7;
- MySQL Server 8.0.46 i MySQL Workbench;
- SQLite jako opcjonalna baza lokalna i baza testowa;
- mysqlclient 2.2.8;
- python-dotenv 1.2.3.

Dokładne wersje zależności są zapisane w [`requirements.txt`](requirements.txt).

## Struktura repozytorium

```text
farmer-app-main/
├── config/                       # ustawienia projektu i główne trasy
├── core/
│   ├── management/commands/      # seed_demo_data
│   ├── migrations/               # migracje aplikacji
│   ├── services/                 # agregacje raportów finansowych
│   ├── templates/core/           # proste szablony Django
│   ├── forms.py, views.py        # formularze i widoki
│   └── test_*.py                 # testy funkcjonalne i bezpieczeństwa
├── docs/
│   ├── database/                 # eksport schematu SQL
│   ├── diagrams/                 # ERD i model Workbench
│   └── dokumentacja_bazy_danych.md
├── .env.example
├── manage.py
└── requirements.txt
```

## Dokumentacja i diagramy

- [Dokumentacja bazy danych](docs/dokumentacja_bazy_danych.md)
- [Diagram ERD](docs/diagrams/erd_farmer_app.png)
- [Model MySQL Workbench](docs/diagrams/farmer_db_model.mwb)
- [Eksport schematu SQL](docs/database/farmer_db_schema.sql)

![Diagram ERD](docs/diagrams/erd_farmer_app.png)

## Instalacja na Windows PowerShell

```powershell
python --version
python -m venv .venv
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Jeśli nie chcesz aktywować środowiska, używaj `.\.venv\Scripts\python.exe` zamiast `python`. Lokalny `.env` trzeba uzupełnić przed uruchomieniem Django; plik jest ignorowany przez Git.

## Konfiguracja `.env`

W obu wariantach ustaw własny, długi i losowy `DJANGO_SECRET_KEY`. Nie kopiuj przykładowych haseł do środowiska produkcyjnego.

SQLite:

```dotenv
DJANGO_SECRET_KEY=change-me-to-a-long-random-value
DJANGO_DEBUG=True
DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1,[::1]
DB_ENGINE=sqlite
```

MySQL:

```dotenv
DJANGO_SECRET_KEY=change-me-to-a-long-random-value
DJANGO_DEBUG=True
DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1,[::1]
DB_ENGINE=mysql
DB_NAME=farmer_db
DB_USER=farmer_app_user
DB_PASSWORD=change-me
DB_HOST=localhost
DB_PORT=3306
```

`DJANGO_DEBUG=False` należy stosować poza środowiskiem deweloperskim. `DJANGO_ALLOWED_HOSTS` jest listą nazw oddzielonych przecinkami. Gdy `DB_ENGINE` nie ma wartości `mysql`, aplikacja korzysta z SQLite.

## Przygotowanie MySQL

Poniższe polecenia wykonaj jako administrator MySQL, zastępując przykładowe hasło:

```sql
CREATE DATABASE farmer_db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'farmer_app_user'@'localhost' IDENTIFIED BY 'change-me-strong-password';
GRANT ALL PRIVILEGES ON farmer_db.* TO 'farmer_app_user'@'localhost';
FLUSH PRIVILEGES;
```

Aplikacja powinna używać dedykowanego konta `farmer_app_user`, a nie `root`.

## Migracje i pierwsze uruchomienie

```powershell
python manage.py check
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver --noreload
```

Aplikacja działa pod `http://127.0.0.1:8000/`, a panel administratora pod `http://127.0.0.1:8000/admin/`.

```powershell
python manage.py makemigrations --check --dry-run
python manage.py showmigrations
python manage.py sqlmigrate core 0001
```

## Dane demonstracyjne

Komenda wymaga istniejącego użytkownika i nie tworzy konta ani hasła:

```powershell
python manage.py seed_demo_data --username admin
```

Tworzy lub aktualizuje rodzaje upraw, dwa pola, uprawy sezonu 2026, prace, opryski i zbiory. Ponowne uruchomienie dla tego samego użytkownika nie duplikuje danych.

## Testy na SQLite

```powershell
$env:DB_ENGINE = "sqlite"
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py test
Remove-Item Env:DB_ENGINE
```

Django tworzy oddzielną bazę testową. Przy testach bezpośrednio na MySQL konto bazy musi zwykle mieć uprawnienie `CREATE`, ponieważ Django tworzy tymczasową bazę z prefiksem `test_`. Zalecanym wariantem lokalnym pozostaje SQLite.

## Workflow Git

```powershell
git switch -c feature/nazwa-zadania
git status
git add <sprawdzone-pliki>
git commit -m "Krótki opis zmiany"
git push -u origin feature/nazwa-zadania
```

Przed scaleniem uruchom pełne testy, `git diff --check` i sprawdź konflikty. `.env`, `db.sqlite3`, `.venv` i dane uwierzytelniające nie mogą trafić do commita. Nazwa gałęzi bazowej i sposób tworzenia pull requestu powinny być zgodne z zasadami zespołu.

## Bezpieczeństwo

- dane gospodarstwa są filtrowane według zalogowanego właściciela;
- cudze obiekty zwracają 404, a relacje w formularzach mają ograniczone querysety;
- formularze POST korzystają z CSRF, wylogowanie i właściwe usuwanie nie odbywają się przez GET;
- hasła są walidowane i hashowane przez Django, a nie przechowywane jawnie;
- `SECRET_KEY`, ustawienia MySQL, `DEBUG` i `ALLOWED_HOSTS` pochodzą ze środowiska;
- na produkcji należy uruchomić także `python manage.py check --deploy` i skonfigurować HTTPS.

## Autorzy

- Imię i nazwisko / numer albumu: _do uzupełnienia_;
- Imię i nazwisko / numer albumu: _do uzupełnienia_;
- Prowadzący: _do uzupełnienia_.
