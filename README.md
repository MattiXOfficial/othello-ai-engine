# othello-python

# Mettre en place l'environnment
Activer l'environnement :
```bash
python3 -m venv .venv --system-site-packages
source .venv/bin/activate
```

Désactiver l'environnment :
```bash
deactivate
```
Installer les dépendances systèmes pour le GUI: (https://pygobject.gnome.org/getting_started.html)
```bash
sudo apt install python3-gi python3-gi-cairo gir1.2-gtk-3.0
```
Installer TOUTES les dépendances : (la partie GUI requiert des dépendances systèmes https://pygobject.gnome.org/getting_started.html)
```bash
pip install -e .
```
Si erreur build backend :
```bash
pip install --upgrade pip setuptools wheel
```
# Lancer le projet
```bash
othello
```
# Tester le projet
```bash
pytest
```

# Créer sa branche à partir de la branche remi
```bash
git switch -c nouvelle-branche remi
```
# Générer la doc
```bash
cd docs
make html
```
# 1 Ajouter de nouvelles traductions (français → anglais) (le commentaire pour supprimer l'erreur flake8)
```bash
print(_("Running in verbose mode"))
```
# 2 Ajouter la traduction correspondante dans le fichier locales/fr/LC_MESSAGES/othello.po
```bash
msgid "Running in verbose mode"
msgstr "Mode verbeux activé"
```
# 3 Compiler le fichier .po en fichier .mo pour que gettext puisse l’utiliser :
```bash
msgfmt locales/fr/LC_MESSAGES/othello.po -o locales/fr/LC_MESSAGES/othello.mo
```