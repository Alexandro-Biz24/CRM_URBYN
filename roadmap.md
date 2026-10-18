session.py

Crée :

engine

SessionLocal

🔹 models/

Chaque fichier = une table SQL.

Les modèles définissent :

colonnes

types

relations

contraintes

Exemples :

tenant

user

company

deal

order

cart

product

Alembic utilise Base.metadata pour générer les migrations.

🔹 schemas/

Modèles Pydantic pour l’API.

Important :
Modèle SQLAlchemy ≠ Schéma API

Les schemas servent à :

Valider les inputs

Structurer les outputs

Exemples :

DealCreate

DealRead

DealUpdate

🔹 repositories/

Contiennent uniquement les requêtes base de données.

Exemple :

get_deal_by_id()

list_deals()

create_deal()

Aucune logique métier ici.

🔹 services/

Contiennent la logique métier.

Exemples :

transitions.py → gérer les changements de statut

rbac.py → vérifier permissions

documents.py → génération PDF

workflows.py → déclenchement n8n

Les services utilisent les repositories.

🔹 api/

Contient les endpoints REST.

Structure :

api/v1/endpoints/

Exemples :

auth

users

deals

orders

metrics

Les endpoints :

appellent les services

retournent des schemas

Ils ne contiennent pas de logique métier complexe.

🔹 utils/

Fonctions utilitaires :

génération d’ID

gestion du temps

helpers techniques

🔁 4. Alembic – Gestion des migrations

Structure :

alembic/
  env.py
  script.py.mako
  versions/

Processus :

Modifier un modèle

Générer migration :

alembic revision --autogenerate -m "message"

Appliquer :

alembic upgrade head

La table alembic_version garde l’historique.

🎨 5. Frontend

Le frontend :

Appelle le backend

Affiche les données

Dessine les graphiques

Gère l’authentification

Il ne contient aucune logique métier.

Il consomme l’API.

🔁 6. n8n – Automatisation

Exemples :

Quand un deal est SIGNED
→ Appel webhook
→ Génération PDF
→ Envoi email

n8n exécute des workflows automatisés.

🌍 7. Multi-tenant

Chaque table contient :

tenant_id

Cela permet :

Une seule base

Plusieurs entreprises

Isolation logique

🔄 8. Flux métier complet

User crée un Cart

Ajoute des produits

Valide le Cart → devient Deal

Deal signé → devient Order

Order completed → revenu comptabilisé

Ensuite :

Le dashboard agrège les données.

📊 9. Dashboard

Endpoints typiques :

GET /metrics/internal

GET /metrics/supplier

Ils renvoient :

total revenue

revenue mensuel

nombre de deals

top fournisseurs

statistiques globales

Un endpoint = toutes les données nécessaires au frontend.

🧪 10. Tests

Structure :

tests/
  test_auth.py
  test_rbac.py
  test_transitions.py

On teste :

login

permissions

transitions métier

🚀 11. Processus pour ajouter une feature

Toujours suivre cet ordre :

Modifier modèle

Générer migration

Appliquer migration

Ajouter repository

Ajouter service

Ajouter endpoint

Ajouter schema

Brancher frontend

🧱 12. Ce qui est déjà fait

Base SQL opérationnelle

Multi-tenant actif

Alembic stable

Modèles propres

Architecture définie

🎯 13. Prochaine étape

Développer dans cet ordre :

CRUD products

CRUD carts

cart → deal workflow

deal → order workflow

endpoints metrics

dashboards frontend

Quand cela fonctionne :

Le CRM est vivant.

🧠 Résumé ultra simple

Backend = cerveau
Frontend = interface
Database = mémoire
Alembic = historien
Repositories = accès mémoire
Services = règles métier
API = porte d’entrée
n8n = robot automatique

Ce projet n’est pas une simple API.

C’est une architecture CRM modulaire prête à évoluer, s’étendre et scaler


crm-suite/
  README.md
  .env.example
  docker-compose.yml              # optionnel (postgres local, redis, etc.)

  backend/
    pyproject.toml
    alembic.ini
    alembic/
      env.py
      script.py.mako
      versions/
        0001_init.py

    app/
      __init__.py
      main.py                     # create_app + include routers
      core/
        config.py                 # settings (.env)
        security.py               # hash pwd, JWT
        deps.py                   # deps FastAPI (get_db, current_user)
        logging.py
      db/
        session.py                # engine + sessionmaker
        base.py                   # Base SQLAlchemy
      models/
        tenant.py
        user.py
        company.py
        contact.py
        deal.py
        order.py
        document.py
        audit_event.py
      schemas/                    # Pydantic (input/output)
        auth.py
        user.py
        deal.py
        order.py
        metrics.py
      repositories/               # accès DB (queries)
        deal_repo.py
        order_repo.py
        metrics_repo.py
      services/                   # logique métier (RBAC, transitions, pdf trigger)
        rbac.py
        transitions.py
        documents.py
        workflows.py              # client n8n (webhook interne)
      api/
        __init__.py
        v1/
          router.py
          endpoints/
            auth.py
            users.py
            deals.py
            orders.py
            documents.py
            metrics.py
      utils/
        ids.py
        time.py

    tests/
      test_auth.py
      test_rbac.py
      test_transitions.py

  frontend/
    package.json
    src/
      app/
      pages/
      components/
      api/                        # client fetch vers backend
      charts/                     # recharts/chartjs
      auth/

  n8n/
    workflows/
      quote_generate.json
      reminders_cron.json

  infra/
    nginx/
    terraform/                    # optionnel




---

# 🧠 3. Comprendre le Backend

Le backend est le **cerveau du système**.

Il est construit avec :

- FastAPI
- SQLAlchemy
- Alembic
- Pydantic
- PostgreSQL

---

## 🔹 main.py

Point d’entrée de l’application.

Responsabilités :

- Créer l’app FastAPI
- Inclure les routers
- Initialiser middleware
- Démarrer l’API

---

## 🔹 core/

Contient les briques fondamentales.

### config.py
- Charge les variables `.env`
- Configure DATABASE_URL, JWT_SECRET, etc.

### security.py
- Hash password
- Génération JWT
- Vérification token

### deps.py
- get_db()
- get_current_user()
- dépendances FastAPI

---

## 🔹 db/

### base.py
Déclare la base SQLAlchemy :

```python
Base = declarative_base()


# 🧠 Architecture Backend & Système CRM – Documentation Technique

---

## 🔹 db/session.py

`session.py` crée :

- `engine` → connexion à la base PostgreSQL
- `SessionLocal` → factory pour créer des sessions DB

Il permet à l’API d’ouvrir et fermer proprement des connexions à la base.

---

## 🔹 models/

Chaque fichier correspond à **une table SQL**.

Les modèles définissent :

- Colonnes
- Types
- Relations
- Contraintes

Exemples de modèles :

- tenant
- user
- company
- deal
- order
- cart
- product

Alembic utilise `Base.metadata` pour générer automatiquement les migrations à partir de ces modèles.

---

## 🔹 schemas/

Les schemas sont des modèles **Pydantic** utilisés par l’API.

Important :

Modèle SQLAlchemy ≠ Schéma API

Les schemas servent à :

- Valider les inputs (requêtes entrantes)
- Structurer les outputs (réponses API)

Exemples :

- DealCreate
- DealRead
- DealUpdate

Ils protègent l’API et définissent ce qui est exposé ou accepté.

---

## 🔹 repositories/

Les repositories contiennent uniquement les **requêtes base de données**.

Exemples :

- `get_deal_by_id()`
- `list_deals()`
- `create_deal()`

Ils ne contiennent **aucune logique métier**.

Ils servent uniquement à accéder aux données.

---

## 🔹 services/

Les services contiennent la **logique métier**.

Exemples :

- `transitions.py` → gérer les changements de statut
- `rbac.py` → vérifier permissions
- `documents.py` → génération PDF
- `workflows.py` → déclenchement n8n

Les services utilisent les repositories.

Ils orchestrent les règles métier du CRM.

---

## 🔹 api/

Contient les endpoints REST.

Structure  DEMANDÉ :


{ role : CLIENT/ADMIN/FOURNISSEUR
demande : description du besoin en output pour le front 
autre : précision exceptionnel mais aps obligatoire 
}










Gestion catalogs pas de suppression 

Table intermedaire multi cat par product et multi produit par cat 

Accompagnement des fournisseur sur le mapping des catalog pour un fournisseur, on fait de historique de tt les connexion inter catalog de la table de liaison 

associé par catalog les attribu obligatoire 


pour les produit :


suppresison de stock 
devise par defaut 
pouvoir modifier le sku_client 


ok 

1) actuellemnt la notion de catalog récurssif avec parent id pour faire des sous catalogs etc c'est trop bien et on peux associer un produit a un catalog odnc les catalog peuvent contenir une multitude produit. 

finalement j'aurais besoin que les produits puissent etre aussi reference dans plusieur catalogs (typiquement deux famille proche ou en prevision de produit hybirde quoi. mais lacomme ça avec juste la table produit et la table catalog je vois pas comment faire est ce qu'il fuat une table intermediaire qui sert de reference ? pour que un catalog liste plusieurs produit et un meme produit soit dans plusieurs catalogue  ? fait moi une ou des proposition pour qu eça soit simple pragmatique et rapide a la reuqete 

2) par conséquent et dans un objectif de faire des propositions de lien d'un produit placé das un catalog avec d'autre catalog 'similaire' j'aurais besoin d'une table meme pas liée au reste de la data base qui juste referencera de maniere UNIQUE les paire de catalog qui on été liée par les fournisseur tt au long de la vie de la DB. et dans un sens unique ça sera un champs from et un champ to 

genre 'from massif beton to Lestage'donc si jamais il y a la paire from lestage to massif beton elle ets bien differnete le sens est IMPORTANT 


3) au niveau de la table produit la logique des attribut separe et modifiebale a la guise c'est TOP mais finalment sur la table product directement, il y a un soucis je vais pas reference 100 paramtere d eprduit a la main. surtotu que chaque ctaalog va avoir des parametre qui leur seront propre donc je devrais pouvoir associé par catalogue des parametre de produit qui leur soit propre. 

donc d'une maniere ou d'une autre il faut que si je suis dans le massif beton et que je créer un produit je vais ecrie dans des champs "poids" "hauteur" "largeur" par exemple, mais ces champs la je pense pas qu'il doivent exister dans la able produit directement, il me faut une table a part je pense que je peux modifier direct via mon interface, par modifier j'entend je créée en tant qu'admin un nouveau catalog je veux en meme temps definir quel sont les attribut/parmaetre des produit de ce catalog que j'autorise a saisir. 
Donc peut etre juste dans la table catalog rajouter un referenicel à une nouvelle table  ou si pas ebsoin juste cette nouvelle table  qui reference justement à partir de l'id d'un catalog dans un champs un nom d'attribut dans un autre champs et un champs de valeur de l'attribut 

et ça se ser gérer direct par api via l'interface donc je peux pas savoir a l'avance si le parametre qui sera créé pour un produti d'un catalog sera en une valeur a chosiir parmis une liste  un str ou un int à la limite c'ets du detail et je ferai un truc full char si il fuat mais si il peut y avoir gestion dynamique de ça sachant que pour chaque attribut de chaque catalog je sai spas si c'est possible dans le champs valeur d'avori different type pour moi non. Donc on laisse de la siasi libre et l apartie restrictive sera gérer dnas le knowledge de l'app. Donc fait moi juste cette nouvellle table liée à catalog pour la  3) qui me permet donc de créer des attribu liée a un catalog direct et efface tout les champs de product SAUF : [catalog_ref
ADMIN_SKU
Client_sku
created_at
updated_at
product_type
is_active
companies_id]

bien entendu. et aussi renomme product_type par product_name stp 



Ok moi ce que je veux c'est très simple. je veux qu'on adapte et ajourte ce qu'il manque au niiveau DB +API + Frontend dans l'interface client + dans l'interface fournisseur, ce qu'il manque pour que : 

1) plusieurs company puisse vendre un produit à leur prix. 
Pour ça il faut qu'on ai une table intermediaire qui refere sur un ligne company id , product id ET price + une colonne "Urbyn_Marge" qui représente le facteur de marge de la plateforme qui sera utile plus tard + une colonne delais, ET une date, date qui se met automatiquement à l'écriture d'un prix ça permet d'avoir un historique des prix. donc en gros une ligen ecrite ne se modiife pas on reecrit une ligne a chaque fois car la date nous servira lorsque tu selectionne un prix pour un produit tu filtre sur les produit tu recupère pour chaque fournisseur le prix le coef et le delais de la ligne aec la DATE la plus récente !!! pour chaque fournisseur la date me servira plus tard pour faire des historique de prix. 

2) mtn que plusieurs prix sont dispo pour un meme produit il faut faire attention il nous faut une nouvelle logique de pricing de panier. 

2.a) par rapport au prix afficher d'un produit ou d'un catalog qui actuellement correspond au prix minimum parmis tt les produit du catalog avec le discount maximum si il en existe 1 dans la selection du nombre de produit. Il faudra adapter la recherche de ce prix minimum d'un catalog ou d'un produit en filtrant donc parmis tt les prix des fournisseurs par produits par catalog etc. 

2.b) Lorsqu'on a selectionné un produit typiquement dans les massifs bétons on met nos filtre et on arrive sur la liste de produits on doit juste voir le noms du produit et le prix minimum du coup dans la mem elogique que le 2.a) 

2.c) Il faut introduire une notion binaire d'abonnement chez les fournisseurs : Simplement tu me met un true false dans une nouvelle table qui renseigne chaque company avec une colonne "abonné" : True/False 


2.d) Lorsqu'on est sur la page ou on choisi la quantité + l'adresse de livriason : il faut impérativement retirer le calcul en direct qui affiche directement le prix des produit puis le prix de livraison des taux de remplsisage de camion etc etc.. mtn il faudra dans cette interfasse sur la droit que le user (client) selectionne son nombre de produit + son adresse de chantier si et seulement si il choisi l'option de livriason, puis cliquer sur un nouveau boutton "estimer ma commande" qui va à partir de l'adresse de livraison saisi par le user (ou rentré automatiquement si le user est deja enregistré chez nous dans nos bases) il faut qu'une route api mega générique avec tt ce contexte aille chercher TOUS les prix + le "Urbyn_Marge" + status d'abonné du fournisseur, de ce meme produit de chaque fournisseur  possible ainsi que leurs adresses associé au catalog qui contient ce fameux produit (fallback : les company qui n'ont pas associé d'adresse ou pour une quelconque raison l'info de l'adresse de company n'existe pas elle n'est pas prise en compte dans le process ok ?) à partir de la il faut calculer le prix de la commande livraison inclu avec exactement le meme systeme de pricing de libraison qui existe actuellement (massif béton à un certain model et totem à un autre model par exemple il faut pas changer le model il faut l'incorporer dans un model qui va calculer l'ensemble de la commande) mais avec les differente combinaison d'adresse entre depart et arrivé, qui viennent des differents fournisseurs attention par combinaison tu me fais pas n'importe quoi : si j'ai trois foirunisseur j'ai 3 combinaison à faire qui devront etre cohérente avec la deuxieme partie du calcul : le calcul de cout des produit : chaque fournisseur renseigne son prix pour le produit donc quand tu me fais une estimation tu me calcul le prix de la commande qui est Livraison (selon adresse fournisseur et l'adresse client rensiegné) + prix unitaire fournisseur ou prix unitaire margé selon l'abonnement True/False * quantité demandé par le user.  Donc si j'ai 3 fournisseur c'est 3 estimation parce que ça marche par paire adresse-prix on melange pas les prix d'un fournisseur avec les adresse d'un autre. 

exempel rapide un produti à 100€ avec un Urbyn_Marge=1.3 si le fournisseur est abonné mon model de pricing de commande= 100€*nb_products + livriason (nb_products). Sinon si il est pas abonné ; commande= (100*1.30)€*nb_products + livriason (nb_products)


2.e) Une fois qu'on a calculé l'ensemble des combinaison possible d'un même produit on va pouvoir faire du trie en 3 segement : 
- prix (le moins cher)
- livraison  (le plus proche)
- délais (le "délais" le moins élevé) (la parimis tt les prix simuler tu filtre simplement sur les delais de chaque fournisseur pour le produits, SI le delais minimum à plusieur fournisseur tu prends celui qui à la simulation de prix la plus faible)

donc le model backend va renvoyer toujours ces 3 segemnt possible bien sur si j'ai que 1 fournisseur bah il sera mis en selection sur les 3 segements logique. mais c'est important de proposé 3 valo differente comme ça les gens prennent ce qu'ils veulent. 

2.f) DB: Plus précisément mtn sur la structure de la DB et surtout l'update des catalog et produit à partir de l'import CSV. vu qu'on  a maintenant une nouvelle table qui fait l'intermediaire avec les prix et les fournisseurs, il me faudrait un tout nouveau pipeline car le csv va avoir un nouveau template avec une nouvelle colonne par defaut (le coeficient de marge Urbyn) + il faut qu'on considère qu'on met forcément par defaut l'entreprise URBANIZE en fournisseur de nimporte quel produit des csv d'import (donc la table intermediaire entre tous les foiurnisseur id et produit id qui reference prix, quantité, dates, délais est toujours existante avec URBANIZE pour TOUS les product ID possible ok ?). avec comme status abonné False, toujours pour URBANIZE ok ?

2.g) donc moi je vais drop un csv on le considère comme le "CSV_ADMIN" avec ces colonnes : ["ID Produit Sellsy",	"Référence",	"Nom commercial",	"Description",	"Prix", "référence HT",	"Coefficient Urbanize",	"Unité",	"Urbyn"	"Nb de massif / palette",	"Passage Fourche",	"Manille Nombre",	"Manille Type",	"Hauteur mât (maximale) en m"	"Largeur (cm)",	"Longueur (cm)",	"Hauteur (cm)",	"Poids (kg",	"Volume (m3)",	"Fournisseur",	"Fichier source"], qui est très similiaire à celui reçu actuellement et qui defini l'arborescence de catalog etc soit de maniere destructive ou additive etc. Donc ça, ça bouge pas on a toute la description de produits attribu etc etc. Seul chose on va feed la nouvelle table intermédiaire avec les prix + le coeficient + delais + il faut obligatoirement considérer sur ce  "CSV_ADMIN" que le fournisseur est Toujours URABNIZE et son status d'abonné vaut par defaut False (dans la table adapté) et pour la table de prix + delai + coef tu remplie la table pour URBANIZE sur chaque produit selon les colonnes "Coefficient Urbanize" + "Prix" + "Délais" c'est le seul cas ou ces table son feeder par l'admin comme ça on s'assure que chaque produit a unecompany et tte les infos qui va avec. 

2.h) Deuxieme CSV (news csv for ingestion purpose ) "CSV_FOURNISSEUR": ce csv il aura juste ces colonnes là :  
["Référence"	"Nom commercial"	"Prix" "référence HT"	"Coefficient Urbanize"	"Urbyn"	"Fournisseur"	"Délais"]

et ce deuxieme CSV lui il va venir referencer chaque produit là ou il fuat car il y a les colonne commune entre les 2 CSV pour se repérer : "Urbyn": va nous indiquer dans quel catalogs se trouve chaque produits,  "Nom commercial" : permet de retrouver precisément le product ID de l'autre table à partir du nom. 
Et donc ce csv sert juste à mettre à jour la ou les table normalisé dans la DB (qu'il va falloir créer) pour renseigner pour chaque paire de produit avec un fournisseur, le prix, le coeficient 

Donc le "CSV_FOURNISSEUR" c'est 1 ligne un produit +1 fournisseur +1 prix + 1 délais. 

2.i) 
Il faut un 3 ème CSV "CSV_ABONNEMENT" : ["Fournisseur",	"Abonnement"]. pour le moment c'est un csv mais on fera un truc automatisé plus tard) avec un CRM, le status d'abonnement ("Abonnement") dans ce CSV c'est juste un fournisseur et un status . donc histoire de modifier que une info sur une seul table pas obligé de reecrire plein de ligne sur les produti ou quoi. 


COMME ça une fois qu'on a feeder la db avec ces 3 CSV on devrait avoir toutes les infos necessaire pour pricer le panier avec multifournisseur sur un produit. on connais les produits, par produit les prix unitaire + les coef + le status d'abonnement de chaque fournisseur + adresse des fournisseur (pour les livraison pricing) 


2.j) donc dans l'interface d'admin il me faudra 3 button 1 button par CSV avec chacun leur propre pipeline, et toujours soit de maniere destructive ou additive. et je suis responsable de la correspondance entre mes colonne de nom produit et les path de catalog dans la colonne Urbyn soit consistante entre CSV admin et CSV fournisseur. Donc il faut des pipelines adapté pour chaque ingestion. 

2.k) Interface fournisseur, je veux dans son interface il doit avoir la la possibilité de voir rangé par catalog quels produits il propose à travers la plateforme avec le prix et le delais associé à chaque produit comme ça le fournisseur peut modifier directement ses prix et delais ! dojnc api vers les champs des table concerné etc t'as compris... 



2.l) check liste : 
- il faut des nouvelles table et modif de certaine table actuel
- pipeline pour feeder ces nouvelle table/table modifié à partir des 3 CSV 
- nouvelle interface admin pour upload les CSVs. 
- nouvelle interface de remplissage de pabier coté client : qunatité adresse --> estimer -> popup choix entre 3 offre delais / prix / livriason --> prix du panier + button ajouter au panier et ça feed le cart. 
- calcul du panier en cours à partir de l'adresse et quantité produit : calcul pour chaque fournisseur un prix de commande (prix unitaire + coef,  conditionné au status abonné ) + prix de livraison (adresse fournissuer adresse client pour connaitre la distance + quantité de produit en param des model de pricing livriaon actuel pour chaque type de servce/produit)
- nouvelle interface coté fournisseur qui concerne directement les produit, on reference dans une interface chaque produit par catalog  pour le fournisseur concerné dans la tbale feedé par le "CSV_FOURNISSEUR" comme ça le fournisseur peut pdater directement son prix ou son abonnement via l'interface (pour le moment il a un button s'abonner mais le button ne fait encore rien). 
- coté client les prix affiché pour les catalog ou produit on cherche le prix minimum avec kles discount possible etc selon les reègles métier. 
- niveau panier quand je veux confirmer la commande, ça ne devrait rien changer nos modifiation je vois toujorus le detail du prix panier complet, les differents camion de livriaosn par typologie etc etc 
- les produits annexe typiquement les manilles ou les fourches ça change rien pour le moment juste pour les prix c'est selon l'offre choisi dans le segement du pop up (delais livraison ou prix) le fournisseur selectionné va donc se charger des prix de manille etc si il les proposes, si il ne propose aucun manille ou quoi on grise l'option de manille. (et on oublie pas le cart est mutialisé donc si pour un produit y'a pas de manille possible mais qu'ensuite le client poursuit sa commande et prends des massif dont le fournissuer fournit des manille etc alors l'option est selectionnable et price, donc les manille seron dispo dans le cart entier et au prochain massif de al meme commande il seront deja selectionné par defaut (la mutualisation est deja en place on la casse pas juste la source est conditionné mtn vu qu'on a plein de fournisseur donc lorsquo'n selectionne un segment tt depend du fournisseur choisi)


3) il me faut dans l'interface un pop up lorsque je choisi un produit et que je demande une estimation en tant que client, en cliquant si le button ça doit calculer tt les estimation et quand ça me renvoie les 3 meilelurs offre par segment je veux un pop up qui me donne le fournisseur et le prix sur chaque segment, donc je vois bien un pop up rectangle  central taille moyenne coupé verticalement en 3 pour chaque segment : delai prix livraison. et chaque segment c'est une sorte de card clicable. et lorsqu'on clique du coup bah popup disparait et on reprend l'interface normal avec le bandeau de droite qui souvre et ou on confirme la mise dans le cart du produit selectionné avec la quantité voulu etc etc go cart ou continer osn shop.. 

4) dans l'interface admin sur les catalog lorsque j'arrive au dernier granularité de catalog et que j'ai ma liste de produit, j'aimerai pouvoir cliquer sur chaque produit comme mtn, mais cette fois ci j'ai une liste de chque fournisseur pour le priduot avec dans la liste une ligne je vois le nom du fournissuer + le prix fournisseur + coef + delai. 

Et dans l'interface d'admin sur les fournissue rje veux un listing des fournisseur enregistré ainsi que leur status d'abonnement. 


FIN  : voilà tt le refactor qu'on dois faire c'ets pas complqiué dans l'idée c'ets juste si le fournisseur paye l'abonnement on vend et affiche ces produti au prix qu'il souhaite si il paye pas d'abonnement on prend une marge sur ces produits. donc ça implique pleind e statu et de verif calcul conditionnelle etc etc mais c'ets pour ça j'ai essayer de segmenter et detaillé chaque point par point pour qu'on fasse step by step. 



PLAN : 
1) j'attend aps que tu me fasse tt d'unn coup et n'importe comment je veux deja qu'on vois si tu as parfaiteemnt compris ce qu'on va faire si chaque etape est claire si tu arrive a me reexliquer point par point ce qui change au niveau de la DB a niveau interface CLIENT au niveau interface ADMIN et interface FOURNISSEUR. Ce qui est attendu pour le coût d'une commande a ajouter dans le panier. (calcul livriason + cout selon chaque fournisseur et leur status...) 

2) tu me porpose le meilleur plan step by step que tu trouve le plus adapter pour qu'on code tout ce refactor 

3) Point important avant de modifier quoi que ce soit dans les DB on va vider  tous les fournisseurs actuel qui ne sont ou ne ressemble pas à :  "ALKERN" "URBANIZE" et "SBC" ils peuvent ne pas etre present dans la base mais al base ne dois rien contenir d'autre j'avais créer pleind e sample pour tester des truc mais maintenant on commence a faire un truc propre ok ? on repart d'un truc propre. 

si il y a plusieurs fois l'entreprise tu me liste tt les "candidat" à chque entreprise et je te dis lequel on garde on aura en 1 et 3 fournsseur à la fin ok ? 

4) je vais tester en mettant les nouveau CSV. 