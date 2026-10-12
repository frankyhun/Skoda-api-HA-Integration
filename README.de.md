# Škoda API Connect für Home Assistant

[🇬🇧 English](README.md) | [🇩🇪 Deutsch](README.de.md) | [🇳🇱 Nederlands](README.nl.md)

Eine mehrsprachige [Home Assistant](https://www.home-assistant.io/)-Custom-Integration für
Škoda-Fahrzeuge auf Basis der offiziellen
[MyŠkoda Public API](https://public.api.connect.skoda-auto.cz/docs). Sie spricht die API
direkt mit einem **API-Schlüssel** an – ohne Benutzername/Passwort und ohne externe
Client-Bibliothek.

> **Inoffizielles Projekt.** Diese Integration steht in keiner Verbindung zu Škoda Auto und wird
> weder von Škoda Auto unterstützt noch empfohlen. Nutzung auf eigene Gefahr.

## Funktionen

Entwickelt nach den aktuellen Best Practices für Home-Assistant-Integrationen: reiner UI-Config-Flow,
`DataUpdateCoordinator` für effizientes Polling, Entity-Beschreibungen, Übersetzungen pro Entity,
Options-Flow, Reauthentifizierung und Diagnose-Download.

| Plattform | Entitäten |
|---|---|
| `sensor` | Batteriestand, Ladeleistung, Ladegrenze (nur lesend), Laderate, verbleibende Ladezeit, Batterie-/Gesamtreichweite, Kraftstoffstand, AdBlue-Reichweite, Kilometerstand, Zieltemperatur, Adresse der Parkposition, Name des aktuell aktiven Ladestandort-Profils, API-Status (Ergebnis der letzten Abfrage, Diagnose), Letzter Abruf (Datum und Uhrzeit des letzten erfolgreichen Abrufs, Diagnose), Rate-Limit bis (wann das Anfragekontingent nach einem Rate-Limit wieder verfügbar ist, Diagnose), Verbleibende API-Anfragen (Rest des Stundenkontingents laut letzter Antwort, mit den Attributen `limit` und `reset_at`, Diagnose) |
| `binary_sensor` | Türen, Fenster, Kofferraum, Motorhaube, Beleuchtung, Zentralverriegelung, Laden, Ladekabel angesteckt, Fahrzeug an gespeichertem Ladestandort |
| `device_tracker` | Parkposition (erscheint auf dem Karten-Dashboard; während der Fahrt unbekannt) |
| `climate` | Standklimatisierung (an/aus, aktive Belüftung, Zieltemperatur) |
| `switch` | Laden starten/stoppen |
| `button` | API jetzt abrufen (ruft die MyŠkoda-API für das Fahrzeug sofort ab; kostet eine Anfrage des API-Kontingents und wird bei aktivem Rate-Limit abgelehnt) |
| `number` | Ladelimit (Ziel-Ladezustand), Abfrageintervalle pro Fahrzeug (normal / beim Laden) |
| `select` | Lademodus |

Sensoren und Steuerungen werden nur für die Daten und Fernbedienungen angelegt, die dein
Fahrzeug tatsächlich meldet. Die Entitätenliste passt sich also an dein Auto an (Elektro, Plug-in-Hybrid
oder Verbrenner).

In den Optionen der Integration lässt sich ein **Nur-Lese-Modus** aktivieren, der alle
Fernsteuerungen deaktiviert und alle Sensoren aktiv lässt.

### Was die öffentliche API nicht bietet

Die Integration nutzt ausschließlich die öffentliche MyŠkoda-API. Folgende Funktionen sind daher
nicht möglich, weil die öffentliche API dafür keinen Endpunkt hat: Ver-/Entriegeln, Hupen &
Blinken, Fahrzeug aufwecken, Scheibenheizung, Batterieschonmodus, reduzierter Ladestrom,
Außentemperatur und Softwareversion. Die Verriegelung ist ein reiner `binary_sensor`.

## Unterstützte Sprachen

Die Integration bringt Übersetzungen für Config-Flow, Options-Flow und Entitätsnamen in folgenden
Sprachen mit:

- English (`en`)
- Nederlands (`nl`)
- Deutsch (`de`)
- Français (`fr`)
- Čeština (`cs`)
- Slovenčina (`sk`)

Home Assistant wählt automatisch die zur Spracheinstellung deiner Instanz passende Übersetzung und
fällt sonst auf Englisch zurück. Beiträge für weitere Sprachen sind willkommen – lege einfach eine
neue Datei unter `custom_components/skoda_api_connect/translations/` an.

Diese Dokumentation gibt es auf [Englisch](README.md), [Deutsch](README.de.md) und
[Niederländisch](README.nl.md).

## Installation

### HACS (empfohlen)

1. Gehe in HACS zu **Integrationen** → Menü (⋮) → **Benutzerdefinierte Repositories**.
2. Füge die Repository-URL (`https://github.com/olafkenfenheuer/Skoda-api-HA-Integration`) mit der
   Kategorie **Integration** hinzu.
3. Suche in HACS nach „Škoda API Connect“, klicke auf **Herunterladen** und installiere die Integration.
4. Starte Home Assistant neu.

### Manuell

1. Lade dieses Repository herunter oder klone es.
2. Kopiere den Ordner `custom_components/skoda_api_connect` in das Verzeichnis
   `config/custom_components/` deiner Home-Assistant-Installation, sodass
   `config/custom_components/skoda_api_connect/manifest.json` existiert.
3. Starte Home Assistant neu.

## Einrichtung

1. Erstelle in der MyŠkoda-App unter <https://go.skoda.eu/api-keys> einen API-Schlüssel und wähle
   die Fahrzeuge aus, für die er gelten soll. Schlüssel sind an diese Fahrzeuge gebunden und laufen ab.
2. Gehe zu **Einstellungen → Geräte & Dienste → Integration hinzufügen** und suche nach „Škoda API Connect“.
3. Gib den API-Schlüssel und die VIN jedes Fahrzeugs ein (mehrere VINs durch Komma getrennt). Die API
   bietet keine Fahrzeugliste, daher müssen die VINs manuell eingegeben werden.
4. Home Assistant prüft den Schlüssel und legt pro Fahrzeug ein Gerät mit allen passenden Entitäten an.
5. Nach der Einrichtung kannst du im Dialog **Konfigurieren** einstellen:
   - das Abfrageintervall (3–1440 Minuten, Standard 10),
   - das kürzere Intervall **während des Ladens** (Standard 5),
   - ob dieses Ladeintervall **auch bei eingestecktem Ladekabel** gilt (Standard aus),
   - den Nur-Lese-Modus.

Den API-Schlüssel (oder die VINs) kannst du jederzeit ersetzen – vor dem Ablauf oder nachdem du einen
neuen erstellt hast – unter **Einstellungen → Geräte & Dienste → Škoda API Connect → ⋮ → Neu konfigurieren**.
Der Eintrag wird neu geladen und behält Entitäten, Verlauf und Optionen.

Läuft der Schlüssel ab (die API meldet `api-key-expired`), zeigt Home Assistant eine
Benachrichtigung zur erneuten Authentifizierung an. Erstelle einen neuen Schlüssel und gib ihn ein,
um die Verbindung wiederherzustellen, ohne den Verlauf der Entitäten zu verlieren.

## Hinweise zur API

Die Integration nutzt ausschließlich die dokumentierten Endpunkte unter
`https://public.api.connect.skoda-auto.cz/api/v1/vehicles/{vin}` und authentifiziert sich über den
Header `X-API-Key`. Die Daten werden per Polling aktualisiert.

### Abfrageintervalle pro Fahrzeug

Jedes Fahrzeug hat zwei `number`-Entitäten (Kategorie Konfiguration): **Abfrageintervall** und
**Abfrageintervall beim Laden**. Sie überschreiben für dieses Fahrzeug die Standardwerte aus den
Integrationsoptionen, gelten sofort ohne Neuladen und lassen sich aus Automationen setzen
(`number.set_value`). Ein Fahrzeug wird mit seinem Ladeintervall abgefragt, sobald der zuletzt
abgerufene Zustand `CHARGING` ist. Mit der Option „Ladeintervall auch bei eingestecktem Ladekabel
verwenden“ gilt es auch, sobald das Ladekabel eingesteckt ist – praktisch, um den Beginn eines
zeitgesteuerten Ladevorgangs zu erfassen, das schnellere Intervall bleibt dann aber aktiv, solange das Auto
angesteckt ist. Nach dem Start eines Ladevorgangs kann es bis zu ein normales Intervall dauern, bis das
schnellere Polling greift; startest du das Laden über Home Assistant, wird das Fahrzeug nach 30 Sekunden
aktualisiert und schaltet sofort um.

Der Schalter **Wenn eingesteckt schnell abfragen** (Kategorie Konfiguration) macht dasselbe pro
Fahrzeug und überschreibt für dieses Fahrzeug die globale Option.

### Ratenlimit

Die API erlaubt derzeit **20 Anfragen pro Stunde und VIN** (laut Dokumentation noch nicht final).
Ein Poll kostet eine Anfrage pro Fahrzeug, jeder Fernbefehl eine weitere. Deshalb:

- Standardintervall 10 Minuten (6 Anfragen/Stunde) bei 5 Minuten Minimum, und 5 Minuten, solange ein
  Fahrzeug lädt bzw. – mit aktivierter Option – eingesteckt ist (12 Anfragen/Stunde – lass Platz für Befehle).
- Nach Befehlen wird nicht jedes Mal aktualisiert; Befehle werden asynchron angenommen (HTTP 202),
  daher wird 30 Sekunden nach dem letzten Befehl einmal aktualisiert.
- HTTP-429-Antworten werden erkannt und das Polling pausiert, für die von der API genannte Wartezeit
  (`Retry-After`, `RateLimit-Reset` oder Fehlermeldung; zuzüglich 30 Sekunden; höchstens 1 Stunde, 15 Minuten ohne Angabe der API); dabei wird eine Warnung protokolliert.
- Der zuletzt bekannte Zustand eines Fahrzeugs bleibt erhalten, wenn nur seine Anfrage fehlschlägt.

Teile des Fahrzeugs, die die API nicht melden kann (zum Beispiel weil das Fahrzeug schläft), fehlen
in der Antwort einfach; die zugehörigen Entitäten werden angelegt, sobald die Daten verfügbar sind,
was ein Neuladen der Integration erfordern kann.

## Entwicklung

```bash
pip install pytest-homeassistant-custom-component
pytest
```

Einen Überblick über Code-Aufbau und Konventionen gibt [CLAUDE.md](CLAUDE.md).

## Changelog

Die Versionshinweise findest du in [CHANGELOG.md](CHANGELOG.md) (Englisch).

## Haftungsausschluss

Bereitgestellt wie besehen, ohne Gewährleistung. Škoda Auto kann seine API jederzeit ändern, wodurch
diese Integration nicht mehr funktionieren kann. Die Nutzung der MyŠkoda Public API unterliegt den
eigenen Nutzungsbedingungen von Škoda.
