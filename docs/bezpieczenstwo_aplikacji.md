# Bezpieczeństwo aplikacji – Farmer App

Dokument opisuje, jak aplikacja jest zabezpieczona: jakie dobre praktyki zastosowano,
które z nich istniały wcześniej, które wdrożono w gałęzi `security/application-hardening`
i jak każde zabezpieczenie zostało sprawdzone. Opis dotyczy poziomu aplikacji Django.
Konfiguracja konkretnego hostingu nie jest jeszcze wybrana.

## 1. Krótki model zagrożeń

**Co chronimy:**

- dane gospodarstw użytkowników: pola, uprawy, prace, opryski, zbiory, finanse, zgłoszenia;
- konta użytkowników: hasła, sesje, tokeny JWT;
- poufną konfigurację: `SECRET_KEY` i dane dostępowe do MySQL.

**Przed kim:**

- anonimowy użytkownik Internetu, np. zgadywanie haseł albo skanowanie formularzy;
- zalogowany użytkownik, który próbuje odczytać lub zmienić dane innego gospodarstwa;
- obca strona WWW, która próbuje wykonać akcję w imieniu zalogowanego użytkownika (CSRF)
  albo osadzić aplikację w ramce (clickjacking);
- osoba podsłuchująca ruch w niezaufanej sieci, np. publicznym Wi-Fi;
- wstrzyknięty skrypt (XSS), np. przez dane wpisane w formularzu.

**Poza zakresem tego dokumentu:**

- bezpieczeństwo serwera, systemu operacyjnego i sieci hostingu;
- konfiguracja TLS na reverse proxy;
- ochrona przed DDoS na poziomie infrastruktury.

## 2. Zagrożenia i zabezpieczenia

| Zagrożenie | Zabezpieczenie | Gdzie zaimplementowano | Jak sprawdzono |
|---|---|---|---|
| Dostęp do cudzych danych (IDOR) | querysety ograniczone do `request.user`; cudzy obiekt → 404; ograniczone listy wyboru w formularzach | `core/views.py`, `core/forms.py` | testy CRUD (`test_fields`, `test_cultivations`, `test_harvests` itd.), `test_security_hardening.ExistingProtectionTests` |
| Dostęp bez logowania | `LoginRequiredMixin` w widokach prywatnych | `core/views.py` | testy przekierowania do logowania |
| CSRF | `CsrfViewMiddleware`, `{% csrf_token %}`, POST dla wylogowania i usuwania, cookie CSRF `SameSite=Lax`, kontrola nagłówka `Origin` z listą `CSRF_TRUSTED_ORIGINS` | `config/settings.py`, szablony | testy z `enforce_csrf_checks=True` (`test_crops`, `test_profile_management`, `test_security_hardening`) |
| Zgadywanie haseł w formularzu | blokada po 5 nieudanych próbach na 15 minut (adres IP + nazwa) | `core/views.py` (`LoginView`) | `test_auth` |
| Zgadywanie haseł przez API | `ScopedRateThrottle` dla endpointów tokenów (10/min, 30/min) | `config/settings.py`, `core/api_views.py` | `test_jwt_auth` |
| Słabe hasła / wyciek bazy | walidatory haseł Django, hashowanie haseł (PBKDF2) | `AUTH_PASSWORD_VALIDATORS` | testy rejestracji i zmiany hasła |
| Wyciek sekretów z repozytorium | `SECRET_KEY`, `DEBUG`, `ALLOWED_HOSTS` i MySQL ze zmiennych środowiskowych; `.env` w `.gitignore` | `config/settings.py`, `.env.example` | `test_database_config` |
| Błędna konfiguracja produkcyjna | ścisłe parsowanie zmiennych logicznych i liczbowych; błąd zamiast cichej wartości domyślnej | `config/settings.py` | `test_security_hardening.SecuritySettingsParsingTests` |
| XSS i wczytanie obcego kodu | autoescape szablonów Django oraz **Content Security Policy** bez `unsafe-inline` i `unsafe-eval` | `SECURE_CSP`, `ContentSecurityPolicyMiddleware` | testy nagłówka CSP i skan wszystkich stron pod kątem kodu inline |
| Clickjacking | `X-Frame-Options: DENY` oraz CSP `frame-ancestors 'none'` | `XFrameOptionsMiddleware`, `SECURE_CSP` | `test_security_hardening.SecurityHeadersTests` |
| Zgadywanie typu MIME | `X-Content-Type-Options: nosniff` | `SECURE_CONTENT_TYPE_NOSNIFF` | test nagłówka |
| Wyciek adresów w nagłówku Referer | `Referrer-Policy: same-origin` | `SECURE_REFERRER_POLICY` | test nagłówka |
| Ataki między oknami (np. tabnabbing) | `Cross-Origin-Opener-Policy: same-origin` | `SECURE_CROSS_ORIGIN_OPENER_POLICY` | test nagłówka |
| Kradzież cookie sesji przez skrypt | `SESSION_COOKIE_HTTPONLY = True` | `config/settings.py` | test cookie |
| Podsłuch w sieci (HTTP) | przekierowanie na HTTPS, cookie `Secure`, HSTS – włączane zmiennymi środowiskowymi | `config/settings.py` | testy przekierowania i cookie, `check --deploy` |

## 3. Mechanizmy istniejące przed tą gałęzią

Te mechanizmy zostały sprawdzone i pozostawione bez zmian (nie zostały zdublowane):

- `SecurityMiddleware`, `CsrfViewMiddleware` i `XFrameOptionsMiddleware` w `MIDDLEWARE`;
- `{% csrf_token %}` we wszystkich formularzach POST. Wylogowanie (`LogoutView`) i właściwe
  usuwanie rekordów działają tylko przez POST, a GET pokazuje stronę potwierdzenia;
- filtrowanie obiektów po `request.user` (`owner`, `field__owner`, `cultivation__field__owner`,
  `user`) i 404 dla cudzych danych, także w listach wyboru formularzy;
- walidatory haseł (`UserAttributeSimilarityValidator`, `MinimumLengthValidator`,
  `CommonPasswordValidator`, `NumericPasswordValidator`) i hashowanie haseł Django;
- blokada logowania po pięciu nieudanych próbach (`LOGIN_MAX_FAILURES = 5`,
  `LOGIN_LOCKOUT_SECONDS = 15 * 60`), liczona w cache dla pary adres IP + nazwa użytkownika;
- JWT (`djangorestframework-simplejwt`): token access na 15 minut, refresh na 1 dzień,
  limity `auth_token` 10/min i `auth_refresh` 30/min;
- `SECRET_KEY`, `DEBUG`, `ALLOWED_HOSTS` i parametry MySQL pobierane ze środowiska. Brak
  `DJANGO_SECRET_KEY` lub danych MySQL zatrzymuje start błędem `ImproperlyConfigured`;
- obsługa konfliktów unikalności przy zapisie jako błąd formularza zamiast błędu 500
  (`UniqueConflictMixin`).

## 4. Mechanizmy dodane w tej gałęzi

| Mechanizm | Dlaczego |
|---|---|
| Content Security Policy przez wbudowany w Django 6.0 `ContentSecurityPolicyMiddleware`: przy `DEBUG=False` wymuszana (`SECURE_CSP`), przy `DEBUG=True` ta sama polityka w trybie raportowania (`SECURE_CSP_REPORT_ONLY`) | druga linia obrony przed XSS: nawet jeśli ktoś wstrzyknie znacznik `<script>`, przeglądarka nie wykona kodu inline ani skryptu z obcej domeny |
| Przeglądarka API DRF (`BrowsableAPIRenderer`) tylko przy `DEBUG=True`; na produkcji wyłącznie `JSONRenderer` | strona narzędziowa DRF używa stylów inline, których wymuszana CSP nie dopuszcza; API dla klientów i tak zwraca JSON |
| Zmienne środowiskowe dla HTTPS: `DJANGO_SECURE_SSL_REDIRECT`, `DJANGO_SESSION_COOKIE_SECURE`, `DJANGO_CSRF_COOKIE_SECURE` | produkcja może wymusić HTTPS i cookie `Secure` bez zmiany kodu, a lokalny HTTP działa dalej |
| HSTS sterowany zmiennymi: `DJANGO_SECURE_HSTS_SECONDS`, `DJANGO_SECURE_HSTS_INCLUDE_SUBDOMAINS`, `DJANGO_SECURE_HSTS_PRELOAD` | HSTS można włączać etapami po wyborze domeny; domyślnie wyłączony |
| `DJANGO_CSRF_TRUSTED_ORIGINS` z walidacją formatu | potrzebne, gdy formularze HTTPS są wysyłane przez inny host lub przez proxy; lista nie przyjmuje `*` ani adresów bez schematu |
| Ścisłe parsowanie wartości logicznych i liczbowych, także `DJANGO_DEBUG` | literówka (np. `Ture`, `-1`, `1.5`) kończy start czytelnym błędem, zamiast po cichu wyłączyć zabezpieczenie. Liczby przyjmują tylko cyfry ASCII `0–9` (najwyżej 10 cyfr), więc `²`, cyfry pełnej szerokości (`３６００`) i bardzo długie ciągi też dają błąd konfiguracji |
| Spójność HTTPS i cookie | przy `DJANGO_SECURE_SSL_REDIRECT=True` cookie sesji i CSRF są domyślnie `Secure`; jawne ustawienie którejś z nich na `False` razem z przekierowaniem zatrzymuje start |
| Walidacja spójności HSTS | `includeSubDomains` i `preload` bez `max-age` albo `preload` bez `includeSubDomains` i roku `max-age` są odrzucane |
| Jawne ustawienia cookie i nagłówków: `SESSION_COOKIE_HTTPONLY`, `SESSION_COOKIE_SAMESITE`, `CSRF_COOKIE_SAMESITE`, `X_FRAME_OPTIONS`, `SECURE_CONTENT_TYPE_NOSNIFF`, `SECURE_REFERRER_POLICY`, `SECURE_CROSS_ORIGIN_OPENER_POLICY` | wartości są widoczne w konfiguracji i chronione testami, więc nie zmienią się niezauważenie przy aktualizacji Django |
| Testy `core/tests/test_security_hardening.py` | sprawdzają konfigurację, nagłówki, cookie, przekierowanie, CSP i dotychczasową ochronę |

`CSRF_COOKIE_HTTPONLY` celowo nie jest włączone. Według dokumentacji Django nie daje
realnej ochrony, bo token i tak trafia do formularzy.

## 5. Content Security Policy

Polityka jest jedna, ale jej tryb zależy od `DJANGO_DEBUG`:

| Tryb | Nagłówek | Działanie |
|---|---|---|
| produkcja, `DJANGO_DEBUG=False` (także gdy zmienna nie jest ustawiona) | `Content-Security-Policy` | przeglądarka **blokuje** wszystko, czego polityka nie dopuszcza |
| rozwój lokalny, `DJANGO_DEBUG=True` | `Content-Security-Policy-Report-Only` | przeglądarka niczego nie blokuje, tylko zapisuje naruszenia w konsoli (F12 → Console) |

Tryb raportowania przy `DEBUG=True` jest potrzebny, bo strony diagnostyczne Django (żółta
strona błędu, strona 404 z listą adresów), domyślna strona błędu CSRF (403) i przeglądarka
API DRF mają style i skrypty inline. Pod wymuszaną polityką straciłyby formatowanie.
Polityka jest ta sama w obu trybach, więc naruszenie w kodzie aplikacji widać lokalnie
w konsoli, zanim trafi na produkcję.

Treść polityki, wysyłanej na każdej odpowiedzi (także w panelu administratora):

```
default-src 'self'; script-src 'self'; style-src 'self' https://fonts.googleapis.com;
font-src 'self' https://fonts.gstatic.com; img-src 'self' data:; connect-src 'self';
object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'
```

| Dyrektywa | Znaczenie i powód |
|---|---|
| `default-src 'self'` | domyślnie tylko zasoby z tej samej domeny |
| `script-src 'self'` | skrypty tylko z plików statycznych (`theme-init.js`, `theme.js`, `forms.js`, skrypty panelu); brak `unsafe-inline` i `unsafe-eval` |
| `style-src 'self' https://fonts.googleapis.com` | `styles.css` oraz arkusz Google Fonts; brak `unsafe-inline` |
| `font-src 'self' https://fonts.gstatic.com` | pliki fontów Google Fonts; `'self'` dla fontów z plików statycznych (np. ikony panelu i przeglądarki API DRF w trybie lokalnym) |
| `img-src 'self' data:` | `data:` jest potrzebne dla obrazka SVG zapisanego w `styles.css` jako `url("data:image/svg+xml,…")` |
| `connect-src 'self'` | aplikacja nie wysyła zapytań `fetch`/XHR do innych domen |
| `object-src 'none'` | blokuje wtyczki (`<object>`, `<embed>`) |
| `base-uri 'self'` | blokuje podmianę adresu bazowego przez wstrzyknięty `<base>` |
| `form-action 'self'` | formularze (logowanie, wylogowanie, zmiana języka, dane) wysyłają dane tylko do tej aplikacji |
| `frame-ancestors 'none'` | strony nie można osadzić w ramce (uzupełnia `X-Frame-Options: DENY`) |

Analiza przed włączeniem polityki:

- szablony nie zawierają `<script>` ani `<style>` inline, atrybutów `style` ani atrybutów
  `on…`. Skrypt motywu `theme-init.js` jest osobnym plikiem;
- jedyne zewnętrzne zasoby to Google Fonts (`fonts.googleapis.com` dla CSS
  i `fonts.gstatic.com` dla plików fontów);
- skrypty motywu ustawiają `root.style.colorScheme` przez CSSOM, czego CSP nie blokuje.
  Zmiana języka to zwykły formularz POST do `/i18n/setlang/`;
- skrypty panelu administratora Django są ładowane z plików statycznych i z `/admin/jsi18n/`
  (ta sama domena); dane dla skryptów trafiają do bloków `<script type="application/json">`,
  których przeglądarka nie wykonuje.

Ponieważ kodu inline nie ma, nonce ani hashe nie są potrzebne. Test `CspCompatibilityTests`
przy wymuszanej polityce renderuje wszystkie główne strony (anonimowe i po zalogowaniu) oraz
strony panelu administratora (logowanie, start, listy, formularz dodawania i edycji)
i sprawdza, że nie zawierają kodu inline, a skrypty, style i obrazy pochodzą tylko
z dozwolonych źródeł.

Uwagi:

- na produkcji przeglądarka API DRF jest wyłączona (`DEFAULT_RENDERER_CLASSES` zawiera tylko
  `JSONRenderer`). Otwarcie adresu API w przeglądarce zwraca JSON. Lokalnie przy
  `DEBUG=True` przeglądarka API działa jak dotąd;
- domyślna strona błędu CSRF (403) ma style inline. Na produkcji wyświetla się pod CSP bez
  formatowania, ale komunikat pozostaje czytelny. Strony diagnostyczne Django przy
  `DEBUG=False` nie są pokazywane;
- panel administratora ma jeden blok `<style>` w liście obiektów, renderowany tylko wtedy,
  gdy akcje masowe są wyłączone. W tym projekcie akcje są włączone.

Ręczna kontrola w przeglądarce: otwórz stronę, narzędzia deweloperskie (F12) → **Console**.
Lokalnie (tryb raportowania) naruszenia są widoczne jako komunikaty „[Report Only] Refused
to load…”, a na produkcji jako „Refused to load…”. Na stronach aplikacji nie powinno ich być.
Sprawdź stronę główną, logowanie, formularze, przełącznik motywu i zmianę języka.

## 6. HTTPS, cookie `Secure` i `CSRF_TRUSTED_ORIGINS`

- `DJANGO_SECURE_SSL_REDIRECT=True` przekierowuje każde żądanie HTTP na HTTPS (301).
- `DJANGO_SESSION_COOKIE_SECURE=True` i `DJANGO_CSRF_COOKIE_SECURE=True` powodują, że
  przeglądarka wysyła cookie tylko przez HTTPS.
- Wszystkie trzy wartości są domyślnie `False`, więc `python manage.py runserver` pod
  `http://127.0.0.1:8000` działa bez przekierowania. Na produkcji włącza się je dopiero
  wtedy, gdy strona jest dostępna przez HTTPS.
- Gdy `DJANGO_SECURE_SSL_REDIRECT=True`, a zmienne cookie nie są ustawione, cookie sesji
  i CSRF automatycznie dostają flagę `Secure`. Jawne `DJANGO_SESSION_COOKIE_SECURE=False` lub
  `DJANGO_CSRF_COOKIE_SECURE=False` razem z przekierowaniem jest sprzeczne i kończy start
  błędem `ImproperlyConfigured`. Odwrotna sytuacja (cookie `Secure` bez przekierowania w
  Django, np. gdy przekierowanie robi proxy) jest dozwolona.
- `DJANGO_CSRF_TRUSTED_ORIGINS` to lista adresów rozdzielonych przecinkami, np.
  `https://farm.example.com`. Każdy element musi mieć schemat `http`/`https` i host, bez
  ścieżki i parametrów. Gwiazdka jest dozwolona tylko jako subdomena
  (`https://*.example.com`), nigdy jako całość. Ustawienie jest potrzebne, gdy formularze
  są wysyłane przez HTTPS z innej domeny niż `Host`, np. za reverse proxy.
- `SECURE_PROXY_SSL_HEADER` **nie jest ustawione**. Jest potrzebne dopiero wtedy, gdy
  aplikacja działa za reverse proxy, które kończy TLS i przekazuje ruch do Django przez HTTP.
  Można je włączyć tylko wtedy, gdy wiadomo, że proxy zawsze usuwa ten nagłówek od klienta
  i ustawia go samo (np. `X-Forwarded-Proto: https`). W przeciwnym razie klient mógłby
  podać nagłówek sam i podszyć się pod połączenie HTTPS. Bez tego ustawienia za takim proxy
  `SECURE_SSL_REDIRECT` powodowałby pętlę przekierowań.

## 7. Etapowe włączanie HSTS

HSTS każe przeglądarce przez określony czas łączyć się z domeną wyłącznie przez HTTPS.
Pomyłki nie da się szybko cofnąć, bo przeglądarki pamiętają ustawienie do końca `max-age`.
Dlatego HSTS jest domyślnie wyłączony (`DJANGO_SECURE_HSTS_SECONDS=0`), a `includeSubDomains`
i `preload` nigdy nie włączają się automatycznie.

1. Wybierz domenę i uruchom HTTPS z ważnym certyfikatem. Ustaw `DJANGO_SECURE_SSL_REDIRECT`
   oraz cookie `Secure` i sprawdź, że cała aplikacja działa przez HTTPS.
2. Ustaw `DJANGO_SECURE_HSTS_SECONDS=300` (5 minut) i sprawdź działanie.
3. Zwiększ wartość do `3600` (godzina), potem `86400` (dzień), `604800` (tydzień)
   i `2592000` (30 dni), obserwując po każdym kroku, czy nie ma problemów.
4. Docelowo ustaw `31536000` (rok).
5. `DJANGO_SECURE_HSTS_INCLUDE_SUBDOMAINS=True` ustaw tylko wtedy, gdy **wszystkie**
   subdomeny działają przez HTTPS.
6. `DJANGO_SECURE_HSTS_PRELOAD=True` ustaw tylko świadomie, przed zgłoszeniem domeny na listę
   preload przeglądarek. Konfiguracja wymaga wtedy `includeSubDomains` i `max-age` co najmniej
   31536000. Usunięcie domeny z tej listy trwa tygodnie lub miesiące.

## 8. Przykład konfiguracji produkcyjnej

Przykład z wartościami zastępczymi. Prawdziwe wartości ustawia się w zmiennych środowiskowych
hostingu, nie w repozytorium:

```
DJANGO_SECRET_KEY=<długa losowa wartość, np. z: python -c "import secrets; print(secrets.token_urlsafe(64))">
DJANGO_DEBUG=False
DJANGO_ALLOWED_HOSTS=farm.example.com
DJANGO_CSRF_TRUSTED_ORIGINS=https://farm.example.com
DJANGO_SECURE_SSL_REDIRECT=True
DJANGO_SESSION_COOKIE_SECURE=True
DJANGO_CSRF_COOKIE_SECURE=True
DJANGO_SECURE_HSTS_SECONDS=300
DJANGO_SECURE_HSTS_INCLUDE_SUBDOMAINS=False
DJANGO_SECURE_HSTS_PRELOAD=False
DB_NAME=<nazwa bazy>
DB_USER=<użytkownik aplikacji>
DB_PASSWORD=<hasło>
DB_HOST=<host MySQL>
DB_PORT=3306
```

Wartości logiczne przyjmują `true/false`, `1/0`, `yes/no`, `on/off`, bez względu na wielkość
liter. Każda inna wartość kończy start aplikacji błędem.

## 9. Serwer produkcyjny

`python manage.py runserver` służy wyłącznie do pracy lokalnej. Nie jest serwerem
produkcyjnym: nie był sprawdzany pod kątem bezpieczeństwa i wydajności. Na produkcji
aplikację uruchamia się przez serwer WSGI/ASGI (np. Gunicorn, uWSGI, Waitress albo
mod_wsgi) za reverse proxy z TLS. Pliki statyczne serwuje proxy albo osobna usługa
(`collectstatic`).

## 10. MySQL: minimalne uprawnienia i kopie zapasowe

- Aplikacja łączy się jako osobny użytkownik (`farmer_app_user`), nigdy jako `root`.
- Lokalnie użytkownik ma `ALL PRIVILEGES` na `farmer_db` i `test_farmer_db`, bo testy tworzą
  i usuwają bazę testową. Na produkcji wystarczy, że konto aplikacji ma
  `SELECT, INSERT, UPDATE, DELETE` na swojej bazie. Migracje (`CREATE, ALTER, INDEX,
  REFERENCES, DROP`) najlepiej wykonywać osobnym kontem używanym tylko podczas wdrożenia.
  Na serwerze produkcyjnym konto nie potrzebuje uprawnień do `test_farmer_db`.
- MySQL powinien przyjmować połączenia tylko z hosta aplikacji, a nie z całego Internetu.
- Kopie zapasowe: regularny `mysqldump` (lub kopia dostawcy hostingu) przechowywany poza
  serwerem bazy, zaszyfrowany i z ograniczonym dostępem. Przywracanie trzeba okresowo
  sprawdzać na osobnej, pustej bazie. Kopie zawierają hashe haseł i dane gospodarstw, więc
  należy je chronić tak jak samą bazę.

## 11. Cache dla blokady logowania i limitów API

Blokada logowania i `ScopedRateThrottle` w DRF przechowują liczniki w cache Django.
Projekt nie ustawia `CACHES`, więc używany jest domyślny `LocMemCache`: pamięć jednego
procesu. Przy kilku procesach serwera (np. kilku workerach Gunicorna) lub kilku serwerach
każdy proces liczy próby osobno, więc rzeczywisty limit się mnoży, a restart zeruje liczniki.
Na produkcji potrzebny jest wspólny cache, np. Redis (`django.core.cache.backends.redis.RedisCache`).

## 12. Polecenia kontrolne

```powershell
python manage.py check
python manage.py check --deploy
python manage.py makemigrations --check --dry-run
python manage.py test
python manage.py test core.tests.test_security_hardening
python -m pip check
```

`check --deploy` należy uruchamiać z konfiguracją produkcyjną (`DJANGO_DEBUG=False`,
prawdziwe `ALLOWED_HOSTS`, flagi HTTPS). Przy lokalnym `.env` z `DJANGO_DEBUG=True` polecenie
słusznie zgłasza ostrzeżenia dotyczące trybu deweloperskiego. Do sprawdzenia podatności
zależności można dodatkowo użyć `pip-audit` (osobne narzędzie, nie jest zależnością projektu).

Wynik `check --deploy` dla tymczasowej konfiguracji produkcyjnej (losowy długi `SECRET_KEY`,
`DEBUG=False`, testowy `ALLOWED_HOSTS`, włączone przekierowanie HTTPS; zmienne cookie
pozostawione puste, więc flaga `Secure` wynika z przekierowania), uruchomionej wyłącznie
przez zmienne środowiskowe procesu:

| Wariant | Ostrzeżenia |
|---|---|
| HSTS = 0 (etap przed wyborem domeny) | `security.W004` – HSTS nie jest ustawiony |
| HSTS = 31536000, bez `includeSubDomains` i `preload` | `security.W005` – brak `includeSubDomains`; `security.W021` – brak `preload` |

Ostrzeżeń nie wyciszono. Zależą od decyzji, które można podjąć dopiero po wyborze domeny
i hostingu (sekcja 7). Innych ostrzeżeń nie było: `SECRET_KEY`, `DEBUG`, `ALLOWED_HOSTS`,
przekierowanie HTTPS, cookie `Secure`, `X-Frame-Options` i `nosniff` są poprawne.
Konfiguracja sprzeczna (`DJANGO_SECURE_SSL_REDIRECT=True` z `DJANGO_SESSION_COOKIE_SECURE=False`)
nie dochodzi do `check --deploy`: start kończy się błędem `ImproperlyConfigured`.

## 13. Ryzyka resztkowe i ustawienia po wyborze hostingu

- Domena, certyfikat TLS i reverse proxy: ustawić `DJANGO_ALLOWED_HOSTS`,
  `DJANGO_CSRF_TRUSTED_ORIGINS`, flagi HTTPS i ewentualnie `SECURE_PROXY_SSL_HEADER`
  (sekcja 6) zgodnie z rzeczywistą konfiguracją proxy.
- HSTS: włączać etapami (sekcja 7).
- Serwer aplikacji: WSGI/ASGI zamiast `runserver`, pliki statyczne przez proxy.
- Wspólny cache (Redis) dla blokady logowania i limitów API przy więcej niż jednym procesie.
- Konto MySQL z minimalnymi uprawnieniami, osobne konto do migracji, kopie zapasowe.
- Blokada logowania jest liczona dla pary IP + nazwa użytkownika. Rozproszony atak z wielu
  adresów nie zostanie zatrzymany. Pomogłyby limity na poziomie proxy albo usługa typu WAF.
- Tokeny JWT nie mają listy unieważnionych tokenów (blacklist). Skradziony token refresh
  działa do końca ważności (1 dzień).
- Zależności trzeba regularnie aktualizować i sprawdzać pod kątem znanych podatności.
- Logi serwera i błędów należy przechowywać bez haseł i tokenów oraz monitorować.
- Google Fonts to zewnętrzna usługa: przeglądarka użytkownika łączy się z serwerami Google.
  Fonty można w przyszłości przenieść do plików statycznych i usunąć domeny Google z CSP.
