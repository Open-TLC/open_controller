# Optimus

Optimus on Open Controllerin parametrien optimointiin suunniteltu ohjelma.

## Toiminta

Optimus sisältää järjestelmän, jolla voidaan kouluttaa RL-malli optimoimaan Open Controllerin extenderien parametreja. Koulutettu malli lukee e1- ja e3-tunnistimilta tiedot ajoneuvojen määristä, ja päättää niiden perusteella uudet parametrit kaikille extendereille. Tarkoituksena on kyetä mukauttamaan parametrit kulloiseenkin liikennetilanteeseen sopiviksi.

## Ajaminen

Optimuksen käyttäminen on pyritty tekemään mahdollisimman helpoksi standardoimalla koko ympäristö Dockeria käyttäen. Ajamiseen tarvitaan ainoastaan Docker ja GNU Make. Ennen ajoa, varmista, että olet muuttanut `optimus/optimus.py` sisällä CONF_ROOT osoittamaan SUMO-simulaation konfiguraatiokansioon. Järjestelmä odottaa, että Open Controllerin konfiguraatiotiedosto löytyy sijainnista `CONF_ROOT/contr/e3.json`. Valmistelujen jälkeen ajaminen onnistuu komennolla:

`make run-optimus`

Tällöin käynnistyy Docker-kontti, joka kouluttaa `optimus/optimus.py` valitsemallasi RL-algoritmilla samassa tiedostossa valitun keston ajan tekoälymallia. Koulutettu malli talletetaan .zip-tiedostoon kansioon `CONF_ROOT/optimus`.

## Arviointi

Koneoppimismallin kouluttaminen sinänsä on hyödytöntä, ja sen toimimisen arvioiminen onkin ensisijaisen tärkeää. Tätä varten Optimus sisältää toisenkin ohjelman, jolla pystytään vertailemaan koulutettuja malleja keskenään. Vertailuohjelma löytyy tiedostosta `optimus/evaluator.py`. Tiedostossa asetetaan jälleen `CONF_ROOT`-muuttuja, sekä vertailtavien mallien nimet. Ohjelmaa ajettaessa, se ajaa identtisen simulaation kaikilla valituilla malleilla, jonka jälkeen se tulostaa jokaisen mallin tuottaman ajoneuvojen keskiviivytyksen, sekä yhteenlasketun viivytyksen koko simulaation ajalta. Tulokset talletetaan myös tiedostoon `CONF_ROOT/out/eval.json`. Arvointiohjelman ajaminen onnistuu komennolla:

`make run-evaluator`

## Nimi

Optimus on yhdistelmä optimointia ja Optimus Primea (ks. Transformers). Syy Optimus Primen käyttämiseen nimessä on se, että Optimus Prime on rekka, mikä sopii näppärästi liikenne-/autoprojektiin. Optimus Primen voidaan myös olettaa toimivan tekoälyllä, mikä niinikään liittyy tiiviisti Optimukseen.

