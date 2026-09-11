# Othello AI Engine

An end-to-end Othello (Reversi) engine built in Python, combining classic adversarial search with machine learning heuristics trained on a database of 25,000+ Grandmaster games.

This was a team academic project at the University of Bordeaux. My primary contribution was the **AI/ML component**: designing and training the move-prediction models and integrating them into the search heuristics.

Team members:
- Remi Boussion: AI part, project structure
- Gregory Bouzon: Data implementation, git management, CLI
- Arthur Voisin: Network part implementation
- Gabriel Ringuet: GUI part

## Highlights

- **Adversarial search**: Minimax with Alpha/Beta pruning, plus Monte Carlo Tree Search (MCTS)
- **Bitboard representation** for fast, memory-efficient board state and move generation
- **Machine learning heuristics** trained on 25k+ Grandmaster games:
  - Random Forest — **81.8%** move-prediction accuracy
  - Custom-built CNN — **78%** move-prediction accuracy
- **Desktop GUI** built with PyGObject/GTK
- **Internationalization (i18n)** — French/English support via `gettext`
- **Auto-generated documentation** via Sphinx

## Tech Stack

Python · scikit-learn · TensorFlow/Keras · PyGObject (GTK) · pytest · Sphinx · gettext

## Team

Built by a team of students at the University of Bordeaux: Matthieu Vigier-Lafosse (AI/ML), Arthur, Gabriel, Gregory, and Remi.

## Getting Started

### 1. Set up the environment

```bash
python3 -m venv .venv --system-site-packages
source .venv/bin/activate
```

To deactivate later:

```bash
deactivate
```

### 2. Install system dependencies (required for the GUI)

The GUI relies on PyGObject/GTK, which needs system-level packages — see the [official getting started guide](https://pygobject.gnome.org/getting_started.html) for other OS/package managers.

```bash
sudo apt install python3-gi python3-gi-cairo gir1.2-gtk-3.0
```

### 3. Install project dependencies

```bash
pip install -e .
```

If you hit a build backend error:

```bash
pip install --upgrade pip setuptools wheel
```

## Usage

Run the game:

```bash
othello
```

Run the test suite:

```bash
pytest
```

Generate the documentation:

```bash
cd docs
make html
```

## Note on data and trained models

The training datasets and trained model files are not included in this repository due to their size (several hundred MB). The code for training and evaluating the models is included in full.

## Contributing / Translations

Add new French → English translations by wrapping strings with `gettext`:

```python
print(_("Running in verbose mode"))
```

Then add the corresponding entry to `locales/fr/LC_MESSAGES/othello.po`:

```po
msgid "Running in verbose mode"
msgstr "Mode verbeux activé"
```

Finally, compile the `.po` file into a `.mo` file so `gettext` can use it:

```bash
msgfmt locales/fr/LC_MESSAGES/othello.po -o locales/fr/LC_MESSAGES/othello.mo
```
