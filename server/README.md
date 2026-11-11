# Serveur de test de l'ERP — guide d'installation

Ce dossier contient tout ce qu'il faut pour transformer un vieux PC sous Ubuntu en
**serveur d'entreprise accessible uniquement par VPN**, comme on le ferait pour un
vrai ERP interne.

> Projet d'apprentissage : chaque étape explique **ce qu'elle fait** et **pourquoi**.

---

## Sommaire

1. [Vue d'ensemble](#1-vue-densemble)
2. [Ce qui va sur le serveur et ce qui va dans Docker](#2-ce-qui-va-sur-le-serveur-et-ce-qui-va-dans-docker)
3. [Contenu du dossier](#3-contenu-du-dossier)
4. [Prérequis](#4-prérequis)
5. [Étape 1 — Copier les scripts sur le serveur](#étape-1--copier-les-scripts-sur-le-serveur)
6. [Étape 2 — DynHost : suivre l'IP publique de la box](#étape-2--dynhost--suivre-lip-publique-de-la-box)
7. [Étape 3 — Ouvrir le port du VPN sur la box](#étape-3--ouvrir-le-port-du-vpn-sur-la-box)
8. [Étape 4 — Installer le serveur WireGuard](#étape-4--installer-le-serveur-wireguard)
9. [Étape 5 — Ajouter un appareil (PC, téléphone)](#étape-5--ajouter-un-appareil-pc-téléphone)
10. [Étape 6 — Tester le VPN](#étape-6--tester-le-vpn)
11. [Étape 7 — Le pare-feu (ufw)](#étape-7--le-pare-feu-ufw)
12. [Étape 8 — Redémarrer et vérifier](#étape-8--redémarrer-et-vérifier)
13. [Opérations courantes](#opérations-courantes)
14. [Dépannage](#dépannage)
15. [Glossaire](#glossaire)

---

## 1. Vue d'ensemble

```
                 Internet
                    │
                    │  seul le port UDP 51820 est ouvert
                    ▼
        ┌───────────────────────┐
        │ Bbox (192.168.1.1)    │  redirige UDP 51820 → serveur
        └───────────┬───────────┘
                    │ réseau local 192.168.1.0/24
                    ▼
        ┌──────────────────────────────────────────────┐
        │ Serveur Ubuntu « <Name> »              │
        │ IP locale : 192.168.1.146                    │
        │ IP VPN    : 10.8.0.1                         │
        │                                              │
        │  ├─ WireGuard (VPN)          ← installé sur  │
        │  ├─ ufw (pare-feu)             le système    │
        │  ├─ DynHost (cron)                           │
        │  │                                           │
        │  └─ Docker Compose           ← l'application │
        │      ├─ Caddy (HTTPS, écoute sur 10.8.0.1)   │
        │      ├─ Front React                          │
        │      ├─ API FastAPI                          │
        │      └─ PostgreSQL (aucun port publié)       │
        └──────────────────────────────────────────────┘

  PC / téléphone (WireGuard) ──tunnel chiffré──► 10.8.0.1 ──► https://erp.<domaine>
```

**Le principe :** depuis Internet, on ne voit qu'une seule porte, celle du VPN.
Le site, le SSH et la base de données ne sont joignables **qu'une fois connecté au
VPN**. C'est exactement le fonctionnement d'un ERP interne en entreprise : même si
quelqu'un connaît l'adresse du site, il ne peut rien en faire sans un accès VPN.

**Les noms de domaine utilisés :**

| Nom                          | Pointe vers                | Rôle                                         |
|------------------------------|----------------------------|----------------------------------------------|
| `server.<domaine>`   | IP publique de la box      | Adresse du VPN (mise à jour par DynHost)     |
| `monitor.<domaine>`  | IP publique de la box      | Supervision (mise à jour par DynHost)        |
| `erp.<domaine>`      | `10.8.0.1` (IP VPN)        | Le site ERP — inaccessible hors VPN          |

---

## 2. Ce qui va sur le serveur et ce qui va dans Docker

| Sur le serveur (ce dossier)          | Dans Docker Compose (racine du projet) |
|--------------------------------------|----------------------------------------|
| WireGuard, ufw, DynHost, SSH, Docker | Caddy, front, API, workers, PostgreSQL |

**Pourquoi cette séparation ?**

- Le VPN et le pare-feu protègent **toute la machine**. Ils doivent fonctionner même si
  Docker est arrêté ou en panne.
- Mettre WireGuard dans un conteneur demanderait des privilèges réseau élevés pour rien.
- Le jour où l'on passe sur **Kubernetes**, seule la partie Docker devient des pods.
  La partie serveur ne change pas : un nœud Kubernetes a lui aussi son VPN et son
  pare-feu en dehors du cluster.
- Les scripts restent **versionnés dans le dépôt** : si le PC lâche, on réinstalle un
  serveur identique en quelques minutes.

---

## 3. Contenu du dossier

```
server/
├── README.md                  ← ce guide
├── ufw.sh                     ← configure le pare-feu
├── dynhost/
│   ├── dynhost.sh             ← met à jour l'IP publique chez OVH
│   ├── dynhost.env.example    ← modèle du fichier d'identifiants
│   ├── dynhost.env            ← tes identifiants (NON versionné, voir .gitignore)
│   └── install.sh             ← installe le script + la tâche cron
└── wireguard/
    ├── setup-server.sh        ← installe et démarre le serveur VPN
    └── add-client.sh          ← crée l'accès VPN d'un appareil
```

---

## 4. Prérequis

- Un PC sous **Ubuntu Server**, branché sur la box.
- Un **nom de domaine chez OVH** (`<domaine>`).
- Des **identifiants DynHost** créés dans l'espace client OVH
  (Domaine → DynHost → Gérer les accès), un par sous-domaine.
- Sur le PC Windows : **PowerShell** (pour `scp` et `ssh`, inclus dans Windows 10/11).
- **Une IP publique non partagée.** Compare l'IP WAN affichée sur la page d'accueil
  de la Bbox avec le résultat de `curl -4 ifconfig.me` sur le serveur.
  Si elles sont identiques, c'est bon. Si elles diffèrent (souvent `100.64.x.x`),
  l'opérateur partage ton IP (**CGNAT**) et aucune redirection de port ne marchera.

---

## Étape 1 — Copier les scripts sur le serveur

Depuis PowerShell, dans le dossier du projet ERP :

```powershell
scp -r server jeremy@192.168.1.146:~/
```

**Ce que ça fait :** `scp` copie le dossier `server` par SSH, à l'identique, dans
`/home/jeremy/server` sur le serveur.

> ⚠️ **Toujours utiliser `scp`, jamais le copier-coller dans un éditeur.**
> Un copier-coller peut ajouter des lignes, changer des guillemets ou les fins de
> ligne. On l'a vécu : `setup-server.sh` s'est abîmé en route et a planté avec
> `unexpected EOF while looking for matching '"'`.

Puis, sur le serveur, rends les scripts exécutables :

```bash
cd ~/server
chmod +x ufw.sh dynhost/*.sh wireguard/*.sh
```

---

## Étape 2 — DynHost : suivre l'IP publique de la box

### Le problème

La box a une **IP publique qui peut changer** (redémarrage, maintenance de l'opérateur).
Les appareils VPN se connectent à `server.<domaine>` : si ce nom pointe vers
une ancienne IP, plus personne ne peut se connecter.

### La solution

Toutes les 5 minutes, le script `dynhost.sh` :

1. récupère l'IP publique actuelle (`ifconfig.me`, avec `api.ipify.org` en secours) ;
2. vérifie qu'il s'agit bien d'une IP valide (sinon il n'envoie rien) ;
3. interroge directement le serveur DNS d'OVH pour connaître l'IP actuellement
   enregistrée (sans passer par un cache) ;
4. **seulement si elles diffèrent**, envoie la nouvelle IP à OVH ;
5. note le résultat dans le journal système.

**Pourquoi DynHost plutôt que l'API OVH ?** Un identifiant DynHost ne peut modifier
**qu'un seul enregistrement**. Si le serveur était compromis, l'attaquant ne pourrait
pas réécrire toute la zone DNS. C'est le principe du **moindre privilège**.

**Pourquoi ne pas mettre à jour à chaque fois ?** OVH peut bloquer un identifiant qui
envoie des mises à jour inutiles en boucle.

### Installation

1. Crée le fichier d'identifiants à partir du modèle :
   ```bash
   cd ~/server/dynhost
   cp dynhost.env.example dynhost.env
   nano dynhost.env
   ```
   Format : `hote:identifiant:motdepasse`, séparés par des espaces :
   ```
   HOSTS="server.<domaine>:<domaine>-ident:MOTDEPASSE monitor.<domaine>:<domaine>-moni:MOTDEPASSE"
   ```

2. Lance l'installation :
   ```bash
   sudo ./install.sh
   ```

**Ce que fait `install.sh` :**

| Action                                         | Pourquoi                                                    |
|------------------------------------------------|-------------------------------------------------------------|
| Installe `dnsutils` (commande `dig`) et `curl` | Pour interroger le DNS et appeler OVH                       |
| Copie le script dans `/opt/dynhost/`           | `/opt` est l'emplacement standard des logiciels ajoutés     |
| Copie les identifiants dans `/etc/dynhost.env` en `chmod 600` | Seul root peut lire les mots de passe        |
| Crée `/etc/cron.d/dynhost`                     | Lance le script toutes les 5 minutes, sans toucher à la crontab de root |
| Lance le script une première fois              | Pour vérifier tout de suite que ça marche                   |

### Vérifier

```bash
journalctl -t dynhost
```

Réponses possibles d'OVH : `good` (mis à jour), `nochg` (pas de changement),
`badauth` (mauvais identifiant/mot de passe). Si rien n'apparaît, c'est normal :
le script ne journalise que lorsqu'il fait une mise à jour ou rencontre une erreur.

---

## Étape 3 — Ouvrir le port du VPN sur la box

Dans l'interface de la Bbox (`192.168.1.1`) → redirection de ports (NAT/PAT) :

| Champ          | Valeur                                         |
|----------------|------------------------------------------------|
| Nom            | `server_wireguard`                             |
| Protocole      | **UDP**                                        |
| Équipement     | `serverjeremy` — `192.168.1.146`               |
| Port externe   | `51820`                                        |
| Port interne   | `51820`                                        |
| IP source      | *(vide : les appareils se connectent depuis n'importe où)* |

**Pourquoi :** la box bloque tout ce qui arrive d'Internet. Cette règle lui dit :
« ce qui arrive sur le port UDP 51820, envoie-le au serveur ». C'est la **seule** porte
ouverte vers l'extérieur.

**Réserve aussi l'IP du serveur** dans le DHCP de la box (adresse MAC
`cc:2f:71:6e:b6:71` → `192.168.1.146`). Sans ça, le serveur peut changer d'IP locale
au redémarrage et la redirection pointera dans le vide.

---

## Étape 4 — Installer le serveur WireGuard

```bash
cd ~/server/wireguard
sudo ./setup-server.sh
```

**Ce que fait le script :**

1. **Installe `wireguard` et `qrencode`.** `qrencode` sert à afficher les QR codes
   pour les téléphones.
2. **Génère la paire de clés du serveur** dans `/etc/wireguard/` :
   - `server.key` : la clé **privée**, qui ne quitte jamais le serveur ;
   - `server.pub` : la clé **publique**, donnée à chaque appareil.

   WireGuard fonctionne comme SSH : chaque côté a une paire de clés, et seuls les
   appareils dont la clé publique est déclarée peuvent se connecter. Pas de mot de passe.
3. **Crée `/etc/wireguard/wg0.conf`.** C'est l'interface réseau virtuelle `wg0` :
   - adresse `10.8.0.1/24` : le serveur dans le réseau VPN ;
   - port d'écoute `51820`.
4. **Active le VPN au démarrage** (`systemctl enable --now wg-quick@wg0`).
5. **Fait démarrer Docker après WireGuard.** Caddy écoutera sur `10.8.0.1`, une adresse
   qui n'existe qu'une fois le VPN monté. Sans cette règle, au redémarrage, Docker
   pourrait démarrer avant le VPN et Caddy planterait.

**Sécurités intégrées :** si `wg0.conf` existe déjà et est complet, il est conservé
(on peut relancer le script sans tout casser). S'il est incomplet, le script s'arrête
et demande de le supprimer.

**Le réseau VPN :**

| Adresse       | Qui                   |
|---------------|-----------------------|
| `10.8.0.1`    | le serveur            |
| `10.8.0.2`    | premier appareil      |
| `10.8.0.3`…   | appareils suivants    |

Les appareils n'ont accès **qu'au serveur**, pas au reste du réseau de la maison.

---

## Étape 5 — Ajouter un appareil (PC, téléphone)

**Règle : un appareil = un accès.** On peut ainsi en révoquer un (PC volé, téléphone
changé) sans toucher aux autres.

### Sur le serveur : générer l'accès

La première fois seulement, enregistre l'adresse publique du VPN sur le serveur.
Elle est gardée dans un fichier **hors du dépôt**, pour ne pas publier ton nom de domaine :

```bash
echo "server.<domaine>:51820" | sudo tee /etc/wireguard/endpoint
```

```bash
cd ~/server/wireguard
sudo ./add-client.sh pc-jeremy
```

**Ce que fait le script :**

1. Vérifie que le serveur WireGuard est bien installé.
2. Choisit la prochaine IP libre (`10.8.0.2`, `10.8.0.3`…).
3. Génère pour l'appareil :
   - sa paire de clés privée/publique ;
   - une **clé pré-partagée** (`PresharedKey`), une couche de chiffrement
     supplémentaire.
4. Déclare l'appareil dans `wg0.conf` (bloc `[Peer]`).
5. Crée le fichier de configuration de l'appareil dans `/etc/wireguard/clients/pc-jeremy.conf`.
6. Recharge WireGuard **sans couper** les connexions en cours (`wg syncconf`).
7. Affiche un QR code.

**Le fichier généré, ligne par ligne :**

```ini
[Interface]
PrivateKey = ...            # clé privée de l'appareil (secrète !)
Address = 10.8.0.2/32       # son adresse dans le VPN

[Peer]
PublicKey = ...             # clé publique du serveur
PresharedKey = ...          # clé partagée avec le serveur
Endpoint = server.<domaine>:51820   # où joindre le serveur (via DynHost)
AllowedIPs = 10.8.0.0/24    # seul le trafic vers le VPN passe dans le tunnel
PersistentKeepalive = 25    # un petit signal toutes les 25 s pour garder la connexion ouverte
```

`AllowedIPs = 10.8.0.0/24` : c'est un **split tunnel**. Seul le trafic vers l'ERP passe
par le VPN. La navigation Internet normale de l'appareil n'est pas ralentie.

### Pour un téléphone

Installe l'application **WireGuard** → `+` → **Scanner un QR code** → scanne le QR code
affiché par le script.

### Pour un PC Windows

1. Sur le serveur, rends le fichier lisible (il appartient à root) :
   ```bash
   sudo cp /etc/wireguard/clients/pc-jeremy.conf ~/
   sudo chown $USER ~/pc-jeremy.conf
   ```
2. Sur le PC (PowerShell) :
   ```powershell
   scp jeremy@192.168.1.146:~/pc-jeremy.conf $HOME\Downloads\
   ```
3. Sur le serveur, supprime la copie (elle contient la clé privée du PC) :
   ```bash
   rm ~/pc-jeremy.conf
   ```
4. Installe **WireGuard pour Windows** (wireguard.com/install) →
   **Importer un ou des tunnels depuis un fichier** → choisis `pc-jeremy.conf` → **Activer**.
5. Supprime le `.conf` de Téléchargements : WireGuard en a gardé sa propre copie.

---

## Étape 6 — Tester le VPN

Depuis l'appareil connecté au VPN :

```bash
ping 10.8.0.1
ssh jeremy@10.8.0.1
```

Sur le serveur, `sudo wg show` doit afficher l'appareil avec un **latest handshake**
de quelques secondes.

> 💡 **Teste depuis l'extérieur** (téléphone en 4G, ou PC sur le partage de connexion
> du téléphone). Beaucoup de box ne savent pas « reboucler » vers leur propre IP
> publique : depuis la maison, le test peut échouer alors que le VPN fonctionne.

---

## Étape 7 — Le pare-feu (ufw)

> ⚠️ Ne lance cette étape **qu'après avoir validé le SSH par le VPN** (étape 6).

```bash
cd ~/server
sudo LAN_SUBNET=192.168.1.0/24 ./ufw.sh
```

**Ce que fait le script :** il installe `ufw` s'il manque, repart de zéro, puis applique :

| Règle                                | Pourquoi                                                    |
|--------------------------------------|-------------------------------------------------------------|
| Tout bloquer en entrée par défaut    | Principe de base : on n'ouvre que ce qui est nécessaire     |
| Tout autoriser en sortie             | Le serveur doit pouvoir faire ses mises à jour, appeler OVH… |
| `51820/udp` depuis partout           | La porte du VPN                                             |
| SSH (22) sur l'interface `wg0`       | Administration uniquement par le VPN                        |
| HTTP/HTTPS (80, 443) sur `wg0`       | L'ERP uniquement par le VPN                                 |
| SSH depuis `192.168.1.0/24`          | **Temporaire** : filet de sécurité pour ne pas s'enfermer dehors |

Une fois que tu as fait au moins une connexion `ssh jeremy@10.8.0.1` réussie, retire
le filet de sécurité :

```bash
sudo ufw delete allow from 192.168.1.0/24 to any port 22 proto tcp
```

### ⚠️ Le piège Docker

**Docker contourne ufw.** Un `ports: "443:443"` dans un `docker-compose.yml` est ouvert
à tout le monde, même si ufw affiche le contraire, car Docker écrit ses propres règles
réseau avant celles d'ufw.

La parade, à appliquer dans le `docker-compose.yml` :

```yaml
caddy:
  ports:
    - "10.8.0.1:443:443"   # écoute uniquement sur l'IP du VPN
    - "10.8.0.1:80:80"

postgres:
  # aucune section "ports" : seule l'API y accède, par le réseau interne de Docker
```

---

## Étape 8 — Redémarrer et vérifier

```bash
sudo reboot
```

Après le redémarrage :

```bash
sudo wg show            # wg0 doit être présent
sudo ufw status         # les règles doivent être actives
journalctl -t dynhost   # le DynHost tourne toujours
```

**Pourquoi redémarrer :** pour vérifier que tout repart **tout seul**, dans le bon ordre
(WireGuard, puis Docker). Un serveur qui ne fonctionne qu'après une intervention
manuelle n'est pas un serveur fiable. C'est aussi l'occasion de charger un nouveau noyau
Linux s'il y en a un en attente (message « Pending kernel upgrade » lors d'un `apt`).

---

## Opérations courantes

### Voir qui est connecté au VPN
```bash
sudo wg show
```

### Lister les appareils
```bash
sudo grep -A0 '^# ' /etc/wireguard/wg0.conf
sudo ls /etc/wireguard/clients/
```

### Retirer l'accès d'un appareil
1. Ouvre `/etc/wireguard/wg0.conf` :
   ```bash
   sudo nano /etc/wireguard/wg0.conf
   ```
2. Supprime le bloc `[Peer]` de l'appareil (repérable à son commentaire `# pc-jeremy`).
3. Recharge sans couper les autres :
   ```bash
   sudo wg syncconf wg0 <(wg-quick strip wg0)
   ```
4. Supprime son fichier :
   ```bash
   sudo rm /etc/wireguard/clients/pc-jeremy.conf
   ```

### Mettre à jour les scripts
Modifie-les sur le PC (dans le dépôt), puis renvoie-les par `scp` (étape 1).

---

## Dépannage

| Symptôme | Cause probable | Solution |
|---|---|---|
| `unexpected EOF while looking for matching '"'` | Script abîmé par un copier-coller | Le renvoyer avec `scp` |
| `$'\r': command not found` | Fichier en fins de ligne Windows (CRLF) | Vérifier `.gitattributes` (`*.sh text eol=lf`), puis `sed -i 's/\r$//' script.sh` |
| `ufw: command not found` | ufw absent de l'installation minimale | `sudo apt install -y ufw` (le script le fait désormais) |
| `add-client.sh` : « Serveur WireGuard non installé » | `setup-server.sh` pas lancé ou en échec | Relancer `sudo ./setup-server.sh` |
| `setup-server.sh` : « wg0.conf … incomplet » | Reste d'une installation ratée | `sudo rm /etc/wireguard/wg0.conf /etc/wireguard/clients/*.conf` puis relancer |
| Le VPN ne se connecte pas depuis la maison | La box ne reboucle pas | Tester en 4G |
| Le VPN ne se connecte nulle part | Redirection de port, CGNAT, IP DynHost fausse | Vérifier la règle de la box, comparer IP WAN / `ifconfig.me`, `dig server.<domaine>` |
| `wg show` : pas de « latest handshake » | Les paquets n'arrivent pas au serveur | Vérifier la box et `sudo ufw status` (51820/udp) |
| `journalctl -t dynhost` : `badauth` | Mauvais identifiant DynHost | Corriger `/etc/dynhost.env` |
| Caddy ne démarre pas après un reboot | Docker démarré avant `wg0` | Vérifier `/etc/systemd/system/docker.service.d/after-wireguard.conf` |

---

## Glossaire

| Terme | Explication |
|---|---|
| **VPN** | Tunnel chiffré qui place un appareil distant « dans » le réseau du serveur |
| **WireGuard** | Logiciel de VPN moderne, simple et rapide, intégré au noyau Linux |
| **Clé publique / privée** | Paire de clés : la privée reste secrète, la publique est partagée. Ce qui est chiffré avec l'une ne se déchiffre qu'avec l'autre |
| **Peer** | Un participant du VPN (le serveur ou un appareil) |
| **Split tunnel** | Seul le trafic vers le VPN passe dans le tunnel, le reste va directement sur Internet |
| **NAT / redirection de port** | Règle de la box qui envoie le trafic d'un port vers une machine du réseau local |
| **CGNAT** | L'opérateur partage une même IP publique entre plusieurs clients : impossible de recevoir des connexions entrantes |
| **DynHost / DNS dynamique** | Mise à jour automatique d'un nom de domaine quand l'IP change |
| **TTL** | Durée pendant laquelle une réponse DNS reste en cache |
| **ufw** | « Uncomplicated Firewall », interface simple pour le pare-feu de Linux |
| **cron** | Planificateur de tâches de Linux (ici : toutes les 5 minutes) |
| **systemd** | Gestionnaire des services Linux (démarrage, ordre, redémarrage) |
| **Moindre privilège** | Donner à chaque composant uniquement les droits dont il a besoin |
| **CRLF / LF** | Fins de ligne Windows / Linux. Un script Linux en CRLF plante |
