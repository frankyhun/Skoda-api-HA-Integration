# Škoda API Connect voor Home Assistant

[🇬🇧 English](README.md) | [🇩🇪 Deutsch](README.de.md) | [🇳🇱 Nederlands](README.nl.md)

Een meertalige [Home Assistant](https://www.home-assistant.io/) custom integration voor
Škoda-voertuigen, gebouwd op de officiële
[MyŠkoda Public API](https://public.api.connect.skoda-auto.cz/docs). De integratie praat
rechtstreeks met de API via een **API-sleutel** - geen gebruikersnaam/wachtwoord en geen
externe client-bibliotheek.

> **Niet-officieel project.** Deze integratie is niet verbonden met, onderschreven door, of
> geassocieerd met Škoda Auto. Gebruik op eigen risico.

## Functies

| Platform | Entiteiten |
|---|---|
| `sensor` | Accuniveau, laadvermogen, laadlimiet (alleen lezen), laadsnelheid, resterende laadtijd, accu-/totaalbereik, brandstofniveau, AdBlue-bereik, kilometerstand, doeltemperatuur, adres van de parkeerpositie, naam van het actieve laadlocatieprofiel, API-status (resultaat van de laatste poll, diagnostisch), laatste poll (datum en tijd van de laatste geslaagde poll, diagnostisch) |
| `binary_sensor` | Deuren, ramen, kofferbak, motorkap, verlichting, centrale vergrendeling, laden, laadkabel aangesloten, voertuig op opgeslagen laadlocatie |
| `device_tracker` | Parkeerpositie (zichtbaar op de kaart; onbekend tijdens het rijden) |
| `climate` | Airco op afstand (aan/uit, actieve ventilatie, doeltemperatuur) |
| `switch` | Laden starten/stoppen |
| `button` | API nu opvragen (vraagt de MyŠkoda-API direct op voor het voertuig; kost één verzoek van het API-quotum en wordt geweigerd tijdens een rate limit) |
| `number` | Laadlimiet (doel-laadniveau), pollinginterval per voertuig (normaal / tijdens laden) |
| `select` | Laadmodus |

Sensoren en bediening worden alleen aangemaakt voor de gegevens en acties die jouw voertuig
meldt. In de opties kun je de **alleen-lezen-modus** inschakelen om alle bediening uit te
zetten.

### Wat de publieke API niet biedt

Deze integratie gebruikt uitsluitend de publieke MyŠkoda-API. Vergrendelen/ontgrendelen,
toeteren & knipperen, voertuig wakker maken, ruitverwarming, accuzorgmodus, gereduceerde
laadstroom, buitentemperatuur en softwareversie zijn daarom niet mogelijk: de publieke API heeft
daarvoor geen endpoint. De vergrendeling is een alleen-lezen `binary_sensor`.

## Ondersteunde talen

De integratie bevat vertalingen voor de config flow, de opties-flow en de entiteitsnamen in:

- English (`en`)
- Nederlands (`nl`)
- Deutsch (`de`)
- Français (`fr`)
- Čeština (`cs`)
- Slovenčina (`sk`)

Home Assistant kiest automatisch de vertaling die overeenkomt met de taalinstelling van je
installatie, met Engels als terugvaloptie. Bijdragen voor extra talen zijn welkom — voeg een
nieuw bestand toe onder `custom_components/skoda_api_connect/translations/`.

Ook deze documentatie is beschikbaar in het [Engels](README.md), het
[Duits](README.de.md) en het [Nederlands](README.nl.md).

## Installatie

### HACS (aanbevolen)

1. Ga in HACS naar **Integraties** → menu (⋮) → **Aangepaste repositories**.
2. Voeg de URL van deze repository toe
   (`https://github.com/olafkenfenheuer/Skoda-api-HA-Integration`) met categorie **Integration**.
3. Zoek in HACS naar "Škoda API Connect", klik op **Downloaden** en installeer de integratie.
4. Herstart Home Assistant.

### Handmatig

1. Download of clone deze repository.
2. Kopieer de map `custom_components/skoda_api_connect` naar de map
   `config/custom_components/` van je Home Assistant-installatie, zodat je uitkomt op
   `config/custom_components/skoda_api_connect/manifest.json`.
3. Herstart Home Assistant.

## Configuratie

1. Maak in de MyŠkoda-app een API-sleutel aan via <https://go.skoda.eu/api-keys> en kies de
   voertuig(en) waarvoor hij geldt. Sleutels zijn aan die voertuigen gebonden en verlopen.
2. Ga naar **Instellingen → Apparaten & services → Integratie toevoegen** en zoek "Škoda API Connect".
3. Voer de API-sleutel en het VIN van elk voertuig in (meerdere VIN's gescheiden door komma's).
   De API heeft geen voertuiglijst, dus de VIN's moeten handmatig worden ingevoerd.
4. Via **Configureren** wijzig je het pollinginterval (3-1440 minuten, standaard 10) of zet je
   de alleen-lezen-modus aan. Optioneel gebruik je het laadinterval ook zolang de laadkabel is aangesloten.

Je kunt de API-sleutel (of de VIN's) op elk moment vervangen - vóór het verlopen of nadat je een nieuwe
hebt aangemaakt - via **Instellingen → Apparaten & services → Škoda API Connect → ⋮ → Opnieuw configureren**.
De invoer wordt herladen en behoudt entiteiten, geschiedenis en opties.

Verloopt de sleutel, dan vraagt Home Assistant om opnieuw te verifiëren: maak een nieuwe sleutel
aan en voer die in.

## Over de API

De integratie gebruikt uitsluitend de gedocumenteerde endpoints onder
`https://public.api.connect.skoda-auto.cz/api/v1/vehicles/{vin}` en authenticeert met de
`X-API-Key`-header.

### Pollinginterval per voertuig

Elk voertuig heeft twee `number`-entiteiten (configuratie): **Pollinginterval** en **Pollinginterval
tijdens laden**. Ze overschrijven de standaardwaarden uit de opties, werken direct zonder herladen
en zijn via automatiseringen in te stellen (`number.set_value`). Zodra de laatst opgehaalde status
`CHARGING` is (of, met de optie "Laadinterval ook gebruiken zolang de laadkabel is aangesloten", zodra de kabel
is aangesloten) wordt het laadinterval gebruikt; na het starten van het laden kan het dus tot één
normaal interval duren voordat het sneller pollen begint (laden starten via Home Assistant ververst
na 30 seconden meteen).

De schakelaar **Snel pollen als kabel is aangesloten** (categorie configuratie) doet hetzelfde per voertuig
en overschrijft voor dat voertuig de algemene optie.

### Rate limits

De API staat momenteel **20 verzoeken per uur per VIN** toe (niet definitief). Een poll kost
één verzoek per voertuig, elk commando nog één. Daarom:

- is het standaardinterval 10 minuten (minimaal 3; 3 minuten gebruiken al de hele limiet van 20 verzoeken per uur, zonder ruimte voor commando's) en 5 minuten tijdens het laden (of bij aangesloten kabel, als je die optie aanzet);
- wordt na commando's slechts één keer ververst, 30 seconden na het laatste commando;
- worden HTTP 429-antwoorden herkend en wordt het pollen gepauzeerd voor de door de API gemelde wachttijd (`Retry-After`,
  `RateLimit-Reset` of foutmelding; plus 30 seconden; maximaal 1 uur, 15 minuten als de API geen wachttijd geeft);
- blijft de laatst bekende status van een voertuig behouden als alleen zijn verzoek mislukt.

## Ontwikkeling

```bash
pip install pytest-homeassistant-custom-component
pytest
```

Zie [CLAUDE.md](CLAUDE.md) voor een overzicht van de code en conventies.

## Changelog

Zie [CHANGELOG.nl.md](CHANGELOG.nl.md) voor de release notes.

## Disclaimer

Aangeboden zoals het is, zonder garantie. Škoda Auto kan zijn API op elk moment wijzigen,
waardoor deze integratie kan stoppen met werken. Gebruik van de publieke MyŠkoda API valt
onder de eigen gebruiksvoorwaarden van Škoda.
