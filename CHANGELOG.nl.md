# Changelog

[🇬🇧 English](CHANGELOG.md) | [🇳🇱 Nederlands](CHANGELOG.nl.md)

Alle relevante wijzigingen aan deze integratie staan hier gedocumenteerd. De indeling volgt
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

## [0.4.0]

### Toegevoegd

- Parkeeralarm: een kritieke melding als een voertuig geparkeerd staat maar niet beveiligd is (betrouwbare vergrendelingsstatus niet `LOCKED`, deuren niet `CLOSED`, deuren vergrendeld niet `YES`, vergrendeld niet `YES` of ramen niet `CLOSED`; onbekende waarden tellen als niet beveiligd, ramen `UNSUPPORTED` wordt overgeslagen). De notify-services die hem krijgen kies je in de opties (meerdere mogelijk); Companion-app-ontvangers krijgen hem als kritieke melding. Eén melding per incident; kost geen API-verzoeken.
- Number "Wachttijd parkeeralarm" per voertuig (schuifregelaar, 0-30 minuten, standaard 5): hoe lang een voertuig onbeveiligd mag blijven voordat de melding wordt verstuurd.
- Binaire sensor "Geparkeerd, niet beveiligd" met de mislukte controles in het attribuut `reasons`.
- Sensors "Deuren vergrendeld", "Betrouwbare vergrendelingsstatus" en "Parkeerstatus", met de waarden zoals de API ze meldt.

### Gewijzigd

- Diagnostics verbergen de ontvangers van het parkeeralarm.

## [0.3.0]

### Toegevoegd

- Sensor "Laatste voertuiggegevens": wanneer het voertuig zelf voor het laatst gegevens naar de Škoda-servers stuurde (nieuwste `carCapturedTimestamp`), met de tijdstempel per onderdeel als attributen. In tegenstelling tot "Laatste poll" laat dit zien wanneer de verbinding tussen auto en servers onderbroken was.
- Knop "Voertuig wakker maken": de API heeft geen wake-up-aanroep, dus de knop stuurt de huidige laadmodus opnieuw (een commando dat niets verandert maar het voertuig moet bereiken), waardoor een slapend voertuig zich meldt. Kost twee verzoeken van het API-quotum.
- Number "Ladend voertuig wekken na (0 = uit)" (configuratiecategorie, standaard uit): als een voertuig laadt en zoveel minuten (stappen van 5, minimaal 10) geen gegevens heeft gemeld, wordt het op dezelfde manier gewekt. Overgeslagen tijdens een rate-limitpauze en als er minder dan 6 verzoeken van het uurquotum over zijn; nooit vaker dan de ingestelde tijd.
- Spaanse en Luxemburgse vertalingen (met dank aan janreimen), inclusief de entiteiten voor het wekken.

### Opgelost

- De Luxemburgse vertaling heet nu `lb.json`; Home Assistant gebruikt de taalcode `lb`, dus `lu.json` werd nooit geladen.

## [0.2.1]

### Opgelost

- Diagnostics bevatten geen VIN's (per-voertuig pollinginstellingen staan nu als `vehicle_1`, `vehicle_2`, ...) en geen voertuignaam meer.

## [0.2.0]

### Toegevoegd

- Binaire sensor "Vergrendeling laadkabel" voor het nieuwe veld `plugLockState` van API 1.1.0 (aan = ontgrendeld).

## [0.1.0]

### Toegevoegd

- Eerste release.
