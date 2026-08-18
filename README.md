# Farmer App

Farmer App to studencka aplikacja internetowa do zarządzania gospodarstwem rolnym. Projekt umożliwia ewidencjonowanie pól, upraw sezonowych, wykonanych prac, oprysków, zbiorów, kosztów i przychodów. Backend został przygotowany w Django i może korzystać z MySQL albo z lokalnej bazy SQLite.

## Główne funkcje

- zarządzanie polami przypisanymi do użytkowników;
- katalog rodzajów upraw;
- planowanie i śledzenie upraw w sezonach;
- rejestrowanie prac polowych i ich kosztów;
- ewidencja oprysków, preparatów i zużytych ilości;
- ewidencja zbiorów, kosztów i przychodów;
- obliczanie wyniku finansowego zbioru;
- obsługa zgłoszeń błędów;
- panel administracyjny Django;
- idempotentna komenda tworząca dane demonstracyjne.

## Technologie

- Python 3.14.6;
- Django 6.0.7;
- MySQL Server 8.0.46 i MySQL Workbench;
- SQLite jako opcjonalna baza lokalna i testowa;
- mysqlclient 2.2.8;
- python-dotenv 1.2.3.

Dokładne wersje zależności znajdują się w [`requirements.txt`](requirements.txt).

## Struktura repozytorium

```text
farmer-app-main/
├── config/                    # ustawienia i konfiguracja projektu Django
├── core/                      # modele, panel admin, testy i logika domenowa
│   ├── management/commands/   # komendy zarządzające, w tym seed_demo_data
│   └── migrations/            # migracje schematu aplikacji core
├── docs/
│   ├── diagrams/              # diagram ERD i model MySQL Workbench
│   └── dokumentacja_bazy_danych.md
├── .env.example               # przykładowe zmienne środowiskowe
├── manage.py
├── requirements.txt
└── README.md
```

## Dokumentacja bazy danych

Kompletna dokumentacja tabel, relacji, walidacji, konfiguracji i kopii zapasowych znajduje się w pliku [docs/dokumentacja_bazy_danych.md](docs/dokumentacja_bazy_danych.md).

### Diagram ERD

![Diagram ERD](docs/diagrams/erd_farmer_app.png)

## Instalacja na Windows

Wymagany jest Python 3.14.6. W PowerShell uruchom:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

Jeżeli polityka PowerShell blokuje aktywację skryptu, można uruchamiać interpreter bezpośrednio jako `.\.venv\Scripts\python.exe`.

## Konfiguracja środowiska

Skopiuj plik przykładowy:

```powershell
Copy-Item .env.example .env
```

Uzupełnij lokalny `.env`. Nie zapisuj w repozytorium prawdziwych haseł ani kluczy:

```dotenv
DJANGO_SECRET_KEY=change-me
DJANGO_DEBUG=True
DB_ENGINE=mysql
DB_NAME=farmer_db
DB_USER=farmer_app_user
DB_PASSWORD=change-me
DB_HOST=localhost
DB_PORT=3306
```

Plik `.env` jest ignorowany przez Git. Jeśli `DB_ENGINE` ma inną wartość niż `mysql` albo nie jest ustawiony, projekt używa SQLite.

## Migracje i uruchomienie

Po skonfigurowaniu docelowej bazy wykonaj:

```powershell
python manage.py migrate
python manage.py createsuperuser
python manage.py check
python manage.py runserver --noreload
```

Aplikacja będzie domyślnie dostępna pod adresem `http://127.0.0.1:8000/`, a panel administracyjny pod `http://127.0.0.1:8000/admin/`.

Przydatne polecenia migracji:

```powershell
python manage.py makemigrations
python manage.py showmigrations
python manage.py sqlmigrate core 0001
```

## Dane demonstracyjne

Najpierw utwórz użytkownika, np. przez `createsuperuser`, a następnie uruchom:

```powershell
python manage.py seed_demo_data --username admin
```

Komenda tworzy przykładowe rodzaje upraw, dwa pola, uprawy na sezon 2026, prace, opryski i zbiory. Można ją uruchamiać wielokrotnie dla tego samego użytkownika — dane zostaną zaktualizowane bez tworzenia duplikatów. Komenda nie tworzy użytkownika ani hasła.

## Testy

Aby wykonać kontrolę i testy na SQLite bez zmiany lokalnego `.env` ani danych MySQL, ustaw silnik tylko w bieżącej sesji PowerShell:

```powershell
$env:DB_ENGINE = "sqlite"
python manage.py check
python manage.py test
Remove-Item Env:DB_ENGINE
```

Testy obejmują walidację modeli, ograniczenia danych, obliczanie zysku oraz poprawność i idempotencję komendy `seed_demo_data`.

## Autorzy

- Imię i nazwisko / numer albumu: _do uzupełnienia_;
- Imię i nazwisko / numer albumu: _do uzupełnienia_;
- Prowadzący: _do uzupełnienia_.
