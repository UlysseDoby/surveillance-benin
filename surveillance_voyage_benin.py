#!/usr/bin/env python3
"""Surveille https://www.voyage.benin.bj/ et envoie un mail dans trois cas :
1. la mention « bientôt disponible » disparaît (signal principal) ;
2. un mot-clé lié à la vente apparaît ;
3. le contenu de la page change.

Chaque lancement effectue plusieurs vérifications espacées de quelques minutes.
Version GitHub Actions : les identifiants mail viennent de variables
d'environnement (secrets du dépôt), jamais écrits dans le code.
"""
import hashlib
import json
import os
import re
import smtplib
import ssl
import time
import unicodedata
from email.message import EmailMessage
from pathlib import Path

import requests

URL = "https://www.voyage.benin.bj/"
ETAT = Path(__file__).with_name("etat_voyage_benin.json")

# Texte comparé sans accents ni majuscules.
MARQUEUR_ATTENTE = r"bientot disponible"

# Mots-clés (sans accents). « vol » et « dates » sont volontairement absents :
# ils figurent déjà sur la page actuelle et déclencheraient de fausses alertes.
MOTS_CLES = {
    "billet": r"\bbillets?\b",
    "billetterie": r"\bbilletterie\b",
    "ticket": r"\btickets?\b",
    "acheter": r"\bacheter\b",
    "achat": r"\bachats?\b",
    "réserver": r"\breserver\b",
    "réservation": r"\breservations?\b",
    "tarif": r"\btarifs?\b",
    "départ": r"\bdeparts?\b",
    "book now": r"\bbook now\b",
    "buy": r"\bbuy\b",
}

SMTP_HOTE = "smtp.gmail.com"
SMTP_PORT = 465
SMTP_UTILISATEUR = os.environ["SMTP_UTILISATEUR"]
SMTP_MOT_DE_PASSE = os.environ["SMTP_MOT_DE_PASSE"]
DESTINATAIRE = os.environ["DESTINATAIRE"]


def normaliser(texte: str) -> str:
    sans_accents = unicodedata.normalize("NFKD", texte)
    sans_accents = "".join(c for c in sans_accents if not unicodedata.combining(c))
    return sans_accents.lower()


def telecharger_texte() -> str:
    r = requests.get(URL, timeout=30, headers={"User-Agent": "Mozilla/5.0"})
    r.raise_for_status()
    html = r.text
    html = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", html)
    texte = re.sub(r"(?s)<[^>]+>", " ", html)
    return normaliser(re.sub(r"\s+", " ", texte).strip())


def envoyer_mail(sujet: str, corps: str) -> None:
    msg = EmailMessage()
    msg["Subject"] = sujet
    msg["From"] = SMTP_UTILISATEUR
    msg["To"] = DESTINATAIRE
    msg.set_content(corps)
    with smtplib.SMTP_SSL(SMTP_HOTE, SMTP_PORT, context=ssl.create_default_context()) as s:
        s.login(SMTP_UTILISATEUR, SMTP_MOT_DE_PASSE)
        s.send_message(msg)


def verifier() -> None:
    texte = telecharger_texte()
    empreinte = hashlib.sha256(texte.encode()).hexdigest()
    trouves = sorted(nom for nom, motif in MOTS_CLES.items() if re.search(motif, texte))
    en_attente = bool(re.search(MARQUEUR_ATTENTE, texte))
    nouvel_etat = {"hash": empreinte, "mots": trouves, "bientot": en_attente}

    ancien = json.loads(ETAT.read_text()) if ETAT.exists() else None
    if ancien is None:
        ETAT.write_text(json.dumps(nouvel_etat))
        print("Première exécution : état enregistré.")
        return

    nouveaux_mots = [m for m in trouves if m not in ancien.get("mots", [])]
    etait_en_attente = ancien.get("bientot", True)

    if etait_en_attente and not en_attente:
        details = f"\nMots-clés détectés : {', '.join(trouves)}" if trouves else ""
        envoyer_mail(
            "La page voyage.benin.bj n'affiche plus « bientôt disponible »",
            f"La vente est peut-être ouverte.{details}\n{URL}",
        )
    elif nouveaux_mots:
        envoyer_mail(
            "Vente de billets : mot-clé détecté sur voyage.benin.bj",
            f"Nouveaux mots détectés : {', '.join(nouveaux_mots)}\n{URL}",
        )
    elif empreinte != ancien["hash"]:
        envoyer_mail("Changement détecté sur voyage.benin.bj", f"La page a changé.\n{URL}")

    # L'état n'est enregistré qu'après l'envoi du mail : si l'envoi échoue,
    # l'alerte sera retentée au passage suivant au lieu d'être perdue.
    ETAT.write_text(json.dumps(nouvel_etat))


def main() -> None:
    passages = int(os.environ.get("NB_PASSAGES", "3"))
    pause = int(os.environ.get("PAUSE_SECONDES", "120"))
    echecs = 0
    for i in range(passages):
        try:
            verifier()
        except Exception as erreur:  # on continue même si un passage échoue
            echecs += 1
            print(f"Erreur au passage {i + 1} : {erreur}")
        if i < passages - 1:
            time.sleep(pause)
    if echecs == passages:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
