# SocaBlock — prototype web

Application Flask + SQLite pour tester :
- inscription / connexion / déconnexion ;
- attribution initiale de 200 SOCA ;
- transferts entre utilisateurs ;
- historique personnel et recherche par clé de partage ;
- notifications contenant la clé de partage ;
- explorateur de blocs avec index, timestamp, hash, previous hash, nonce et difficulté ;
- génération automatique contrôlable depuis l'explorateur : un bloc vide toutes les 2 secondes ; chaque transfert crée immédiatement son propre bloc ;
- nonce calculé par preuve de travail et affiché pour chaque bloc ;
- tableau de bord avec le nombre de blocs et le temps écoulé depuis le premier bloc ;
- profil avec affichage facultatif de sa propre clé privée, masquée par défaut ;
- affichage compact des blocs, avec les détails accessibles à la demande ;
- génération de blocs avec preuve de travail et difficulté réglable ;
- profil et compteurs de transactions.

## Versionnement
La version courante est indiquée dans `VERSION`. Chaque modification publiée doit
mettre à jour cette version selon SemVer et être accompagnée d'un tag Git `v<version>`.
La version initiale est `0.1.0`.

## 1. Pré-requis
- Python 3.10 ou plus récent
- VS Code

## 2. Installation Windows (PowerShell)
Ouvre le dossier `SocaBlock` dans VS Code, puis le terminal intégré :

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
python app.py
```

Si PowerShell bloque l'activation :
```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\venv\Scripts\Activate.ps1
```

## 3. Ouvrir l'application
Dans le navigateur : http://127.0.0.1:5000

Crée deux comptes avec deux adresses e-mail différentes pour tester un transfert.
La base `socablock.db` est créée automatiquement au premier démarrage.

## 4. Parcours de test
1. Crée le compte A : il reçoit 200 SOCA.
2. Crée le compte B dans un autre navigateur privé ou après déconnexion.
3. Connecte-toi avec A et envoie par exemple 25 SOCA à B.
4. Chaque transfert crée immédiatement un bloc lié à la chaîne et visible dans l'historique de l'expéditeur comme du destinataire. Les blocs vides continuent d'être ajoutés toutes les 2 secondes ; le bouton de l'explorateur permet d'arrêter puis de reprendre cette génération automatique.
5. Depuis la page Blockchain, tu peux aussi générer manuellement un bloc avec une difficulté de 1 à 4.
6. Connecte-toi avec B : la notification contient la clé de partage.
7. Colle cette clé dans Historique pour retrouver le transfert.

## Notes importantes de sécurité et de conception
Ce projet est un prototype local d'apprentissage, pas une cryptomonnaie ni un réseau décentralisé prêt pour la production.
- La clé privée Ed25519 est ici conservée non chiffrée dans SQLite pour simplifier la démonstration. Ne déploie pas cette version sur Internet avec de vrais fonds ou données sensibles.
- La clé de partage est un jeton aléatoire propre à une transaction. La clé publique Ed25519 identifie le signataire ; elle n'est pas, à elle seule, une clé de recherche de transaction.
- La signature est produite avec la clé privée de l'expéditeur. Une prochaine étape devra vérifier systématiquement cette signature à la lecture.
- Le solde SOCA et la chaîne sont centralisés dans une seule base SQLite. La preuve de travail ajoutée est pédagogique et limitée à la génération locale de blocs ; il n'y a pas de consensus entre plusieurs nœuds, d'API publique ni de protection contre les accès concurrents avancés.
- Le mode debug est activé pour le développement local uniquement.
