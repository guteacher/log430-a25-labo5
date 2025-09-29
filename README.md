# Labo 05 – Microservices SOA et SBA, API Gateway, Rate Limit & Timeout

<img src="https://upload.wikimedia.org/wikipedia/commons/2/2a/Ets_quebec_logo.png" width="250">    
ÉTS - LOG430 - Architecture logicielle - Chargé de laboratoire: Gabriel C. Ullmann, Automne 2025.

## 🎯 Objectifs d'apprentissage
- Apprendre à communiquer avec un microservice déjà existant
- Apprendre à configurer et utiliser krakend, un API Gateway
- Découvrir les configurations de `timeout` (limitation du temps de réponse) et `rate limiting` (limitation du nombre de requêtes) dans krakend

## ⚙️ Setup

Dans ce labo, nous allons ajouter des fonctionnalités de paiement à notre application `store_manager`. Ainsi comme nous avons les répertoires `orders` et `stocks` dans notre projet, nous pourrions simplement ajouter un répertoire `payments` et commencer à écrire nos fonctionnalités de paiement. Cependant, il vaut mieux développer une application complètement isolée dans un dépôt séparé - un microservice - pour les paiements en lieu de l'ajouter au `store_manager`. Ça nous donne plus de flexibilité de déploiement et évolution. Pour en savoir plus, veuillez lire la documentation architecturale dans le répertoire `/docs/arc42/architecture.pdf`.

> ⚠️ ATTENTION : Pendant ce laboratoire, nous allons travailler avec ce dépôt (`log430-a25-labo5`), ainsi qu'avec un **deuxième dépôt**, `log430-a25-labo5-paiement`. Veuillez lire le document `/docs/adr/adr001.md` dans `log430-a25-labo5-paiement` pour comprendre notre choix de créer un microservice séparé pour les fonctionnalités de paiement.

### 1. Clonez les dépôts
Créez vos propres dépôts à partir des dépôts gabarits (templates). Vous pouvez modifier la visibilité pour les rendre privés si vous voulez.
```bash
git clone https://github.com/guteacher/log430-a25-labo5
git clone https://github.com/guteacher/log430-a25-labo5-paiement
cd log430-a25-labo5
```
Ensuite, clonez votre dépôt sur votre ordinateur et sur votre serveur de déploiement (ex. VM). Veillez à ne pas cloner le dépôt d'origine.

Ensuite, veuillez faire les étapes de setup suivantes pour les **deux dépôts**.

### 2. Créez un fichier .env
Créez un fichier `.env` basé sur `.env.example`. Dans le fichier `.env`, utilisez les mêmes identifiants que ceux mentionnés dans `docker-compose.yml`. Veuillez suivre la même approche que pour les derniers laboratoires.

### 3. Créez un réseau Docker
Exécutez dans votre terminal :
```bash
docker network create labo05-network
```

### 4. Préparez l'environnement de développement
Suivez les mêmes étapes que pour les derniers laboratoires.
```bash
docker compose build
docker compose up -d
```

### 5. Préparez l'environnement de déploiement et le pipeline CI/CD
Utilisez les mêmes approches qui ont été abordées lors des derniers laboratoires.

## 🧪 Activités pratiques

### 1. Intégration du service de paiement
Modifiez l'endpoint `POST /orders` dans `store_manager.py` pour qu'à chaque nouvelle commande, il demande un lien de paiement au service de paiement et sauvegarde ce lien dans la base de données.

Modifiez la fonction `request_payment_link`, qui est appelée à chaque création de commande :
```python
def request_payment_link(order_id, total_amount, user_id):
    payment_request = {
        "user_id": user_id,
        "order_id": order_id,
        "total_amount": total_amount
    }
    # POST http://payments_web_service:5009/payments/add
    # ATTENTION: n'utilisez pas localhost, car localhost n'existe pas dans Docker, seulement les hostnames des services
```

> 💡 **Question 1** : Quelle réponse obtenons-nous à la requête à http://payments_web_service:5009/payments/add ? Illustrez votre réponse avec des captures d'écran/terminal.

### 2. Utilisez le lien de paiement
- Utilisez la collection Postman qui est dans `docs/collections` à `log430-a25-labo5`
- Créez une commande. Vous obtiendra un `order_id`
- Faites une requête à `payments/process/:order_id` en utilisant le `order_id` obtenu. Regardez l'onglet "Body" pour voir ce qu'on est en train d'envoyer dans la requête.
- Ensuite, ouvrez la collection sur `docs/collections` qui est dans `log430-a25-labo5-payment`
- Faites une requête à `POST payments/:order_id`
- Observez le résultat pour savoir se le paiement a éte realisé correctemnt.

> 💡 **Question 2** : Quel type d'information nous obtenons en appelant `POST payments/:order_id`? Illustrez votre réponse avec des captures d'écran/terminal.

> 💡 **Question 3** : Quel type d'information envoie-t-on dans la requête ? Est-ce que ce serait le même format si on communiquait avec un service SOA, par exemple ? Illustrez votre réponse avec des exemples et captures d'écran/terminal.

### 3. Installez et configurez l'API Gateway
Comme vous avez vu, pour appeler un service il faut utiliser son hostname (ex. http://payments_web_service:5009) ou adresse IP. Cependant, quelquefois dans un grand projet, les services changent de réseau, IP ou nom au fil du temps. Comment éviter de changer le code quand ça arrive ? On peut utiliser un API gateway tel que KrakenD.

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

Créez le fichier de configuration `config/krakend.json`. Initialement, on ne va ajouter qu'un seul endpoint :
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
      "endpoint": "/api/payments",
      "method": "POST",
      "backend": [
        {
          "url_pattern": "/payments",
          "host": ["http://payments_web_service:5009"],
          "timeout": "5s"
        }
      ]
    }
  ]
}
```

Testez les routes `/api/orders` et `/api/payments` via Postman.

### 4. Testez le rate limiting avec Locust

En plus de fonctionner en tant qu'une façade pour nos APIs, nous pouvons aussi utiliser KrakenD pour limiter l'accès à nos APIs et les protéger des attaques DDOS, par exemple. Nous faisons ça avec rate limiting. Créez un nouveau test dans `locust/locustfile.py` spécifiquement pour tester le rate limiting :

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

> 💡 **Question 4** : À partir de combien de requêtes par minute observez-vous les erreurs 429 ? Justifiez avec des captures d'écran de Locust.

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

## 📦 Livrables

- Un fichier .zip contenant l'intégralité du code source du projet Labo 05.
- Un rapport en .pdf répondant aux questions présentées dans ce document. Il est obligatoire d'illustrer vos réponses avec du code ou des captures d'écran/terminal.