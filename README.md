# Labo 05 – Microservices SOA et SBA, API Gateway, Rate Limit & Timeout

<img src="https://upload.wikimedia.org/wikipedia/commons/2/2a/Ets_quebec_logo.png" width="250">    
ÉTS - LOG430 - Architecture logicielle - Chargé de laboratoire: Gabriel C. Ullmann, Automne 2025.

## 🎯 Objectifs d'apprentissage
- Apprendre la distinction entre les microservices SOA et SBA 
- Apprendre à configurer et utiliser un API Gateway
- Découvrir les configurations de base d'un API Gateway telles que timeout et rate limiting

## ⚙️ Setup

Notre magasin a maintenant été racheté par une chaîne de magasins qui possède déjà son système de paiement SOA hérité (PaymentServiceSOA). Dans ce laboratoire, nous apprendrons comment communiquer avec ce système avec des messages XML et aussi comment transformer ce système SOA pour le rendre SBA (Service-Based Architecture).

> ⚠️ **IMPORTANT** : Avant de commencer le setup et les activités, veuillez lire la documentation architecturale dans le répertoire `/docs/arc42/architecture.pdf`.

### 1. Clonez le dépôt
Créez votre propre dépôt à partir du dépôt gabarit (template). Vous pouvez modifier la visibilité pour la rendre privée si vous voulez.
```bash
git clone https://github.com/guteacher/log430-a25-labo5
cd log430-a25-labo5
```
Ensuite, clonez votre dépôt sur votre ordinateur et sur votre serveur de déploiement (ex. VM). Veillez à ne pas cloner le dépôt d'origine.

### 2. Créez un fichier .env
Créez un fichier `.env` basé sur `.env.example`. Dans le fichier `.env`, utilisez les mêmes identifiants que ceux mentionnés dans `docker-compose.yml`. Veuillez suivre la même approche que pour le laboratoire 01.

### 3. Créez un réseau Docker
Si pas déjà créé, exécutez dans votre terminal :
```bash
docker network create labo05-network
```

### 4. Préparez l’environnement de développement
Suivez les mêmes étapes que dans le laboratoire 01.
```bash
docker compose build
docker compose up -d
```

### 5. Préparez l’environnement de déploiement et le pipeline CI/CD
Utilisez les mêmes approches qui ont été abordées lors des dernièrs laboratoires.


## 🧪 Activités pratiques

Dans ce laboratoire, nous allons intégrer un service de paiement SOA existant avec notre store manager et implémenter un API Gateway avec des fonctionnalités de rate limiting et timeout.

### 1. Intégration du service de paiement
Modifiez l'endpoint `POST /orders` dans `store_manager.py` pour qu'à chaque nouvelle commande, il demande un lien de paiement au service de paiement et sauvegarde ce lien dans la base de données.

D'abord, ajoutez une nouvelle colonne `payment_link` à la table `orders` :
```sql
ALTER TABLE orders ADD COLUMN payment_link VARCHAR(500);
```

Ensuite, modifiez la fonction de création de commande :
```python
import requests
import xml.etree.ElementTree as ET

@app.post('/orders')
def post_orders():
    # ... code existant pour créer la commande ...
    
    # Demander un lien de paiement au service SOA
    payment_request = f"""
    <paymentRequest>
        <orderId>{order_id}</orderId>
        <amount>{total_amount}</amount>
        <userId>{user_id}</userId>
    </paymentRequest>
    """
    
    response = requests.post(
        'http://payment-service:8080/payment/create-link',
        data=payment_request,
        headers={'Content-Type': 'application/xml'}
    )
    
    if response.status_code == 200:
        # Parser la réponse XML
        root = ET.fromstring(response.text)
        payment_link = root.find('paymentLink').text
        
        # Sauvegarder le lien dans la base de données
        # ... code pour UPDATE de la table orders ...
    
    # ... reste du code ...
```

> 💡 **Question 1** : Quelle est la différence principale entre la communication SOA (avec XML) et SBA (avec JSON/REST) que vous observez dans cette intégration ? Justifiez votre réponse avec des exemples de code.

### 2. Implémentez le webhook de notification de paiement
Créez un nouvel endpoint dans `store_manager.py` pour recevoir les notifications du service de paiement :

```python
@app.post('/payment/notification')
def payment_notification():
    # Recevoir la notification XML du service de paiement
    xml_data = request.data.decode('utf-8')
    
    try:
        root = ET.fromstring(xml_data)
        order_id = root.find('orderId').text
        payment_status = root.find('status').text  # 'SUCCESS' ou 'FAILED'
        
        # Mettre à jour le statut de la commande dans la base de données
        # ... code pour UPDATE ...
        
        return {"status": "notification received"}, 200
    except Exception as e:
        return {"error": str(e)}, 400
```

> 💡 **Question 2** : Pourquoi cette approche n'est-elle pas un "vrai" webhook ? Quelles sont les limitations de cette implémentation par rapport à un système de webhook moderne ?

### 3. Installez et configurez l'API Gateway
Ajoutez KrakenD comme API Gateway dans votre `docker-compose.yml` :

```yaml
  krakend:
    image: devopsfaith/krakend:2.4
    container_name: krakend-gateway
    ports:
      - "8080:8080"
    volumes:
      - ./config/krakend.json:/etc/krakend/krakend.json
    networks:
      - labo05-network
    depends_on:
      - store-manager
```

Créez le fichier de configuration `config/krakend.json` :
```json
{
  "version": 3,
  "name": "Store Manager API Gateway",
  "timeout": "5s",
  "cache_ttl": "300s",
  "output_encoding": "json",
  "port": 8080,
  "endpoints": [
    {
      "endpoint": "/api/orders",
      "method": "GET",
      "backend": [
        {
          "url_pattern": "/orders",
          "host": ["http://store-manager:5000"],
          "timeout": "5s"
        }
      ],
      "extra_config": {
        "qos/ratelimit/router": {
          "max_rate": 10,
          "capacity": 10
        }
      }
    },
    {
      "endpoint": "/api/orders",
      "method": "POST", 
      "backend": [
        {
          "url_pattern": "/orders",
          "host": ["http://store-manager:5000"],
          "timeout": "5s"
        }
      ],
      "extra_config": {
        "qos/ratelimit/router": {
          "max_rate": 10,
          "capacity": 10
        }
      }
    },
    {
      "endpoint": "/api/test/slow",
      "method": "GET",
      "backend": [
        {
          "url_pattern": "/test/slow",
          "host": ["http://store-manager:5000"],
          "timeout": "5s"
        }
      ]
    }
  ]
}
```

### 4. Testez le rate limiting avec Locust
Créez un nouveau test dans `locust/locustfile.py` spécifiquement pour tester le rate limiting :

```python
@task(1)
def test_rate_limit(self):
    """Test pour vérifier le rate limiting"""
    response = self.client.get("/api/orders")
    if response.status_code == 429:  # Too Many Requests
        print("Rate limit atteint!")
```

Accédez à `http://localhost:8089` et configurez Locust avec :
- Number of users : 20
- Spawn rate : 5 (par seconde)

Lancez le test et observez les réponses 429 (Too Many Requests) qui apparaissent quand la limite de 10 requêtes par minute est dépassée.

> 💡 **Question 3** : À partir de combien de requêtes par minute observez-vous les erreurs 429 ? Comment le rate limiting protège-t-il votre API contre les attaques par déni de service ? Justifiez avec des captures d'écran de Locust.

### 5. Créez une route de test pour le timeout
Ajoutez un endpoint de test qui simule une réponse lente :

```python
import time

@app.get('/test/slow')
def test_slow_endpoint():
    """Endpoint pour tester les timeouts"""
    delay = request.args.get('delay', default=3, type=int)
    time.sleep(delay)  # Simule une opération lente
    return {"message": f"Response after {delay} seconds"}, 200
```

Testez différents délais à travers KrakenD :
- `GET localhost:8080/api/test/slow?delay=2` (devrait fonctionner)
- `GET localhost:8080/api/test/slow?delay=10` (devrait timeout avec une erreur 503)

> 💡 **Question 4** : Que se passe-t-il quand vous faites une requête avec un délai supérieur au timeout configuré (5 secondes) ? Quelle est l'importance du timeout dans une architecture de microservices ? Justifiez votre réponse avec des exemples pratiques.

### 6. Analysez les métriques de l'API Gateway
KrakenD fournit des métriques automatiquement. Vous pouvez les visualiser en activant l'endpoint de métriques en ajoutant cette configuration dans votre `krakend.json` :

```json
{
  "extra_config": {
    "telemetry/metrics": {
      "collection_time": "60s",
      "proxy_disabled": false,
      "router_disabled": false,
      "backend_disabled": false,
      "endpoint_disabled": false,
      "listen_address": ":8090"
    }
  }
}
```

Redémarrez KrakenD et accédez aux métriques sur `http://localhost:8090/__stats`.

> 💡 **Question 5** : Quelles métriques l'API Gateway vous fournit-il qui ne seraient pas disponibles en accédant directement au service ? Comment ces métriques peuvent-elles aider dans le monitoring d'une architecture de microservices ?

### 7. Transformation SOA vers SBA
Créez une nouvelle version de l'endpoint de notification qui accepte du JSON au lieu de XML :

```python
@app.post('/payment/notification/v2')
def payment_notification_v2():
    """Version SBA de la notification de paiement"""
    try:
        data = request.get_json()
        order_id = data['orderId']
        payment_status = data['status']
        
        # Même logique de mise à jour mais avec JSON
        # ... code ...
        
        return {"status": "notification received"}, 200
    except Exception as e:
        return {"error": str(e)}, 400
```

> 💡 **Question 6** : Comparez les deux approches (SOA avec XML vs SBA avec JSON). Quels sont les avantages et inconvénients de chaque approche en termes de performance, lisibilité, et maintenabilité ? Justifiez avec des exemples de code.

## 📦 Livrables

- Un fichier .zip contenant l'intégralité du code source du projet Labo 05.
- Un rapport en .pdf répondant aux questions présentées dans ce document. Il est obligatoire d'illustrer vos réponses avec du code ou des captures d'écran/terminal.
- Les configurations KrakenD (krakend.json) et les tests Locust utilisés.
- Des captures d'écran montrant :
  - Les métriques de rate limiting dans Locust
  - Les erreurs de timeout (503) de KrakenD
  - Les statistiques KrakenD sur `/__stats`