#!/usr/bin/env python3
"""Surveille https://www.voyage.benin.bj/ et envoie un mail si la page change
ou si un mot-clé lié à la vente de billets apparaît.

Version GitHub Actions : les identifiants mail viennent de variables
d'environnement (secrets du dépôt), jamais écrits dans le code.
"""
import hashlib
import json
import os
import re
import smtplib
import ssl
from email.message import EmailMessage
from pathlib import Path

import requests

URL = "https://www.voyage.benin.bj/"
ETAT = Path(__file__).with_name("etat_voyage_benin.json")

# Mots-clés qui signalent l'ouverture de la vente (à adapter)
MOTS_CLES = ["billet", "billetterie", "ticket", "acheter", "réserver", "reserver", "book now", "buy"]

SMTP_HOTE = "smtp.gmail.com"
SMTP_PORT = 465
SMTP_UTILISATEUR = os.environ["SMTP_UTILISATEUR"]
SMTP_MOT_DE_PASSE = os.environ["SMTP_MOT_DE_PASSE"]
DESTINATAIRE = os.environ["DESTINATAIRE"]


def telecharger_texte() -> str:
    r = requests.get(URL, timeout=30, headers={"User-Agent": "Mozilla/5.0"})
    r.raise_for_status()
    html = r.text
    html = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", html)
    texte = re.sub(r"(?s)<[^>]+>", " ", html)
    return re.sub(r"\s+", " ", texte).strip().lower()


def envoyer_mail(sujet: str, corps: str) -> None:
    msg = EmailMessage()
    msg["Subject"] = sujet
    msg["From"] = SMTP_UTILISATEUR
    msg["To"] = DESTINATAIRE
    msg.set_content(corps)
    with smtplib.SMTP_SSL(SMTP_HOTE, SMTP_PORT, context=ssl.create_default_context()) as s:
        s.login(SMTP_UTILISATEUR, SMTP_MOT_DE_PASSE)
        s.send_message(msg)


def main() -> None:
    texte = telecharger_texte()
    empreinte = hashlib.sha256(texte.encode()).hexdigest()
    trouves = sorted(m for m in MOTS_CLES if m in texte)

    ancien = json.loads(ETAT.read_text()) if ETAT.exists() else None
    ETAT.write_text(json.dumps({"hash": empreinte, "mots": trouves}))

    if ancien is None:
        print("Première exécution : état enregistré.")
        return

    nouveaux_mots = [m for m in trouves if m not in ancien["mots"]]
    if nouveaux_mots:
        envoyer_mail(
            "Vente de billets : mot-clé détecté sur voyage.benin.bj",
            f"Nouveaux mots détectés : {', '.join(nouveaux_mots)}\n{URL}",
        )
    elif empreinte != ancien["hash"]:
        envoyer_mail("Changement détecté sur voyage.benin.bj", f"La page a changé.\n{URL}")


if __name__ == "__main__":
    main()
