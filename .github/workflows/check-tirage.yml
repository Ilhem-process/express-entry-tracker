name: Surveillance tirages Entrée express

on:
  schedule:
    # Toutes les 15 minutes
    - cron: "*/15 * * * *"
  workflow_dispatch: {}  # permet de lancer manuellement depuis l'onglet Actions

permissions:
  contents: write  # nécessaire pour committer le fichier d'état

jobs:
  verifier-tirage:
    runs-on: ubuntu-latest
    steps:
      - name: Cloner le dépôt
        uses: actions/checkout@v4

      - name: Installer Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.11"

      - name: Vérifier s'il y a un nouveau tirage
        env:
          TELEGRAM_BOT_TOKEN: ${{ secrets.TELEGRAM_BOT_TOKEN }}
          TELEGRAM_CHAT_ID: ${{ secrets.TELEGRAM_CHAT_ID }}
        run: python check_tirage.py

      - name: Sauvegarder l'état si changé
        run: |
          if [ -n "$(git status --porcelain dernier_tirage.json)" ]; then
            git config user.name "github-actions[bot]"
            git config user.email "github-actions[bot]@users.noreply.github.com"
            git add dernier_tirage.json
            git commit -m "Mise à jour du dernier tirage connu"
            git push
          else
            echo "Aucun changement à sauvegarder."
          fi
