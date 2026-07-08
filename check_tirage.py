#!/usr/bin/env python3
"""
Vérifie UNE FOIS s'il y a un nouveau tirage Entrée express (Express Entry)
IRCC, et envoie une notification Telegram si c'est le cas.

Conçu pour être exécuté périodiquement par GitHub Actions (cron), plutôt
qu'en boucle infinie sur un PC local.

Configuration requise (secrets GitHub Actions ou variables d'environnement) :
  - TELEGRAM_BOT_TOKEN
  - TELEGRAM_CHAT_ID
"""

import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

EE_JSON_URL = "https://www.canada.ca/content/dam/ircc/documents/json/ee_rounds_123_en.json"
FALLBACK_API_URL = "https://can-ee-draws.karanjit-sagun01.workers.dev/api/draws/latest"
STATE_FILE = "dernier_tirage.json"


def envoyer_telegram(message: str) -> None:
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    data = json.dumps({
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "HTML",
    }).encode("utf-8")
    req = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            resp.read()
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="ignore")
        print(f"Erreur envoi Telegram (HTTP {e.code}) : {detail}")
        sys.exit(1)
    except Exception as e:
        print(f"Erreur envoi Telegram : {e}")
        sys.exit(1)


def recuperer_dernier_tirage(tentatives: int = 4):
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
        ),
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "fr-CA,fr;q=0.9,en;q=0.8",
    }
    derniere_erreur = None
    for essai in range(1, tentatives + 1):
        try:
            req = urllib.request.Request(EE_JSON_URL, headers=headers)
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            rounds = data.get("rounds", [])
            if rounds:
                return normaliser_tirage_officiel(rounds[0])
        except Exception as e:
            derniere_erreur = e
            print(f"Tentative {essai}/{tentatives} (source officielle) échouée : {e}")
        if essai < tentatives:
            time.sleep(10)

    # Source officielle inaccessible après plusieurs essais (probablement
    # bloquée pour les IP de centres de données) : on tente une source de
    # secours tierce, hébergée sur Cloudflare, qui republie les mêmes
    # données à partir d'IRCC.
    print("Source officielle inaccessible, tentative via la source de secours...")
    try:
        req = urllib.request.Request(
            FALLBACK_API_URL, headers={"Accept": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        tirage_brut = data.get("data", data) if isinstance(data, dict) else data
        if isinstance(tirage_brut, list) and tirage_brut:
            tirage_brut = tirage_brut[0]
        if tirage_brut:
            return normaliser_tirage_secours(tirage_brut)
    except Exception as e:
        derniere_erreur = e
        print(f"Source de secours échouée aussi : {e}")

    raise derniere_erreur


def normaliser_tirage_officiel(tirage: dict) -> dict:
    return {
        "numero": tirage.get("drawNumber"),
        "date": tirage.get("drawDate"),
        "type": tirage.get("drawName"),
        "crs": tirage.get("drawCRS"),
        "invitations": tirage.get("drawSize"),
    }


def normaliser_tirage_secours(tirage: dict) -> dict:
    # Extraction tolérante : les noms de champs exacts de cette API tierce
    # n'ont pas pu être vérifiés à l'avance, donc on essaie plusieurs
    # variantes courantes.
    def premier_present(*cles):
        for cle in cles:
            if cle in tirage and tirage[cle] not in (None, ""):
                return tirage[cle]
        return None

    return {
        "numero": premier_present("drawNumber", "number", "round", "id"),
        "date": premier_present("drawDate", "date"),
        "type": premier_present("drawName", "category", "type", "program"),
        "crs": premier_present("drawCRS", "crs", "score", "crsScore"),
        "invitations": premier_present("drawSize", "invitations", "size", "itas"),
    }


def charger_dernier_numero_connu():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f).get("drawNumber")
    return None


def sauvegarder_dernier_numero(numero: str) -> None:
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump({"drawNumber": numero}, f)


def formater_message(tirage: dict) -> str:
    return (
        "🇨🇦 <b>Nouveau tirage Entrée express !</b>\n\n"
        f"Numéro du tirage : {tirage.get('numero')}\n"
        f"Date : {tirage.get('date')}\n"
        f"Type de tirage : {tirage.get('type')}\n"
        f"Score CRS minimum : {tirage.get('crs')}\n"
        f"Invitations émises : {tirage.get('invitations')}\n"
    )


def main():
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("Erreur : TELEGRAM_BOT_TOKEN ou TELEGRAM_CHAT_ID manquant.")
        sys.exit(1)

    dernier_connu = charger_dernier_numero_connu()
    try:
        tirage = recuperer_dernier_tirage()
    except Exception as e:
        print(f"Échec de la récupération après plusieurs tentatives : {e}")
        sys.exit(1)

    if tirage is None:
        print(f"[{datetime.now()}] Aucune donnée reçue.")
        return

    numero_actuel = tirage.get("numero")

    if dernier_connu is None:
        # Premier lancement : on enregistre sans notifier.
        sauvegarder_dernier_numero(numero_actuel)
        print(f"Référence initialisée sur le tirage #{numero_actuel}.")
    elif numero_actuel != dernier_connu:
        print(f"Nouveau tirage détecté : #{numero_actuel}")
        envoyer_telegram(formater_message(tirage))
        sauvegarder_dernier_numero(numero_actuel)
    else:
        print(f"Pas de nouveau tirage (dernier connu : #{dernier_connu}).")


if __name__ == "__main__":
    main()
