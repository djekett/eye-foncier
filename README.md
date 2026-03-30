# 🗺️ EYE-FONCIER

**Plateforme WebSIG de Transaction Foncière Sécurisée**

Application web complète développée avec Django 5.0, PostGIS et Leaflet pour la gestion sécurisée de transactions foncières avec cartographie interactive, coffre-fort documentaire et traçabilité complète.

---

## 🏗️ Architecture

```
eye-foncier/
├── eyefoncier/          # Configuration Django
│   ├── settings.py      # Paramètres (PostGIS, JWT, cache, sécurité)
│   ├── urls.py          # Routage principal
│   ├── context_processors.py
│   └── wsgi.py
├── accounts/            # Gestion utilisateurs & rôles
├── parcelles/           # Cœur SIG — parcelles, zones, îlots
├── documents/           # Coffre-fort documentaire sécurisé
├── transactions/        # Réservations & ventes
├── websig/              # Interface cartographique
├── templates/           # Templates Django (Bootstrap 5 + Leaflet)
├── static/              # CSS, JS, images
├── media/               # Fichiers uploadés
├── logs/                # Journaux applicatifs
├── requirements.txt     # Dépendances Python
├── manage.py
└── .env.example         # Variables d'environnement
```

## ✨ Fonctionnalités

### 🗺️ WebSIG Interactif

- Carte Leaflet avec couches GeoJSON temps réel
- Basemaps : satellite, rues, topographique
- Filtres dynamiques (type, prix, surface, statut)
- Géolocalisation utilisateur
- Recherche spatiale (bbox, rayon)

### 🔐 Sécurité Renforcée

- Rôles différenciés : Visiteur, Acheteur, Vendeur, Géomètre, Admin
- Documents consultables uniquement avec filigrane dynamique (pas de téléchargement)
- Hash SHA-256 pour intégrité des fichiers
- Journal d'accès complet (IP, user-agent, horodatage)
- Authentification JWT pour l'API REST

### 📄 Coffre-Fort Documentaire

- Upload sécurisé (PDF)
- 3 niveaux de confidentialité : public, acheteurs, privé
- Filigrane automatique avec ReportLab
- Traçabilité complète des consultations

### 💰 Transactions

- Workflow : En attente → Réservé → Payé → Finalisé / Annulé
- Références auto-générées
- Mise à jour automatique du statut parcelle

### ✅ Système de Confiance

- Badge de confiance automatique (titulaire = propriétaire)
- Validation géomètre (vérification GPS)
- KYC utilisateur

## 🔧 Prérequis

- **Python** 3.11+
- **PostgreSQL** 16+ avec **PostGIS** 3.4+
- **GDAL** 3.6+
- **Redis** 7+ (cache & sessions)

## 🚀 Installation

### 1. Cloner et configurer

```bash
cd eye-foncier
cp .env.example .env
# Éditez .env avec vos paramètres
```

### 2. Base de données

```sql
CREATE USER eye_foncier_user WITH PASSWORD 'Lynkwb123.';
CREATE DATABASE eye_foncier_db OWNER eye_foncier_user;
\c eye_foncier_db
CREATE EXTENSION postgis;
```

### 3. Environnement Python

```bash
python -m venv venv
source venv/bin/activate  # Linux/Mac
pip install -r requirements.txt
```

### 4. Migrations & lancement

```bash
python manage.py makemigrations accounts parcelles documents transactions websig
python manage.py migrate
python manage.py createsuperuser
python manage.py collectstatic --noinput
python manage.py runserver
```

Accédez à : **http://localhost:8000**

## 📡 API REST

| Endpoint                            | Méthode | Description                   |
| ----------------------------------- | ------- | ----------------------------- |
| `/api/v1/auth/token/`               | POST    | Obtenir un token JWT          |
| `/api/v1/auth/token/refresh/`       | POST    | Rafraîchir le token           |
| `/api/v1/auth/register/`            | POST    | Inscription                   |
| `/api/v1/auth/me/`                  | GET     | Profil courant                |
| `/api/v1/parcelles/geojson/`        | GET     | Parcelles GeoJSON (filtrable) |
| `/api/v1/parcelles/geojson/<uuid>/` | GET     | Détail parcelle               |
| `/api/v1/parcelles/nearby/`         | GET     | Recherche par rayon           |
| `/api/v1/parcelles/zones/`          | GET     | Zones GeoJSON                 |
| `/api/v1/parcelles/ilots/`          | GET     | Îlots GeoJSON                 |
| `/api/v1/transactions/`             | GET     | Mes transactions              |
| `/api/v1/transactions/<uuid>/`      | GET     | Détail transaction            |

## 🎨 Rôles Utilisateurs

| Rôle         | Accès                                             |
| ------------ | ------------------------------------------------- |
| **Visiteur** | Carte, infos limitées                             |
| **Acheteur** | Docs filigrannés, infos propriétaire, réservation |
| **Vendeur**  | Ajout parcelles/médias/docs, suivi ventes         |
| **Géomètre** | Validation GPS des parcelles                      |
| **Admin**    | Accès complet, logs, modération                   |

## 🏭 Production

```bash
# Gunicorn
gunicorn eyefoncier.wsgi:application --bind 0.0.0.0:8000 --workers 4

# Nginx reverse proxy recommandé
# Configurez HTTPS avec Let's Encrypt
# Activez le stockage S3 dans .env
```

## 📋 Technologies

- **Backend** : Django 5.0, Django REST Framework, GeoDjango
- **Base de données** : PostgreSQL 16, PostGIS 3.4
- **Frontend** : Bootstrap 5.3, Leaflet 1.9, Bootstrap Icons
- **Sécurité** : JWT, SHA-256, ReportLab (watermark)
- **Cache** : Redis

---

**EYE-FONCIER** — Sécuriser les transactions foncières par la technologie.
"# Eye-Africa-foncier" 
