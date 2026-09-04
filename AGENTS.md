# Project Rules & Architecture Guidelines (Ren'Py Live Translator)

## 1. Règle de synchronisation automatique du plugin
Pour toute modification ou mise à jour apportée au fichier `plugin/00_translator.rpy` :
1. **Toujours synchroniser automatiquement le plugin dans le jeu testé :**
   Copier immédiatement `plugin/00_translator.rpy` vers :
   `/Applications/renpy-8.4.1-sdk/DepravedAwakening.app/Contents/Resources/autorun/game/00_translator.rpy`
2. **Nettoyer le cache compilé :**
   Supprimer systématiquement `/Applications/renpy-8.4.1-sdk/DepravedAwakening.app/Contents/Resources/autorun/game/00_translator.rpyc` pour garantir que Ren'Py recharge et exécute la toute dernière version.

## 2. Règles d'Or Architecturales Anti-Régression
Pour préserver la stabilité, la fluidité (60 FPS) et la persistance des traductions :

1. **Activation native de la langue Ren'Py :**
   Toujours définir `config.default_language = target_folder` et appeler `renpy.change_language(target_folder)` au niveau de `init 999 python:`. Sans cela, Ren'Py ignore le sous-dossier `tl/<lang>/` et affiche l'anglais par défaut.
2. **Résolution infaillible des chemins (`_get_game_dir`) :**
   Ne JAMAIS se fier uniquement à `os.getcwd()` (qui pointe vers `/` ou `~` sur macOS `.app`). Toujours inspecter `__file__`, `config.gamedir`, `config.basedir` et valider la présence de `tl/` ou `00_translator.rpy`.
3. **Persistance fichier + Injection immédiate en mémoire :**
   Toute nouvelle traduction doit être enregistrée dans `game/tl/<lang>/live_translations.rpy` ET injectée à chaud dans `renpy.game.script.translator.strings[lang].translations[source_text]` pour un affichage instantané sans redémarrage.
4. **Interdiction de surcharger les classes en cascade :**
   Ne JAMAIS monkey-patcher simultanément `Character.__call__`, `renpy.exports.say` et `Text.__init__`. Seuls `config.say_menu_text_filter` et `renpy.translation.translate_string` (protégé par `is_dialogue_text`) doivent être utilisés pour éviter 4 à 5 appels HTTP redondants par réplique.
5. **Timeout réseau suffisant :**
   La constante `TIMEOUT` doit toujours être $\ge 4.0\text{s}$ (ex: `4.5s`) pour laisser aux moteurs de traduction le temps de traiter les phrases longues sans déclencher de faux timeout.
6. **Limites d'init Ren'Py :**
   Les priorités `init` sont strictement bornées entre `-999` et `999`.

## 3. Validation Obligatoire
Avant de clore une intervention, TOUJOURS exécuter la suite de tests de non-régression :
```bash
python3 tests/test_live_translator.py
```
Les 33 tests unitaires et de non-régression doivent impérativement être validés (OK).
