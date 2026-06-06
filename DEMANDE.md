DEMANDE 1: 
{
role : FOURNISSEUR
demande : Le forunisseur dois pouvoir créer un compte avec ses information necessaire a l'identification (c'est a dire tous les champs disponible sur les models de table postgre sql dispo dans le projet qui concerne l'identification du Fournisseur) je veux pour une prmeiere etape une route dédier a la création d'un "compte" exclusivement pour les fournisseur donc le front renverra un json avec toutes les infos et la route doit feed la DB avec ces infos et verifier bien sur si les info de Primary key ne sont pas deja existante genre mail nom prenom etc etc. 
autre : voici dans l'ordre il faut traiter les champs et les tables qui devront etre remplie atention il y a u split selon si la company existe deja ou non : 

1) table : users
id -> automatique 
email -> saisi par le user 
password_hash -> créer par le user vu qu'on est sur un login 
is_active -> par default = True 
created_at -> automatique des time stamp de cration 
updated_at -> automatique des time stamp des que y a un update  
role_id -> role id vu qu'on est sur la creation du compte fournisseur ce sera toujours 1 sur cette requete. Car le role etant fournisseur et l'id role correspondant est le 1. 
mobile_phone -> saisi 
fixe_phone -> saisi 

2) table user_profiles : 
id 
user_id -> liée à l'id generé sur la table "users" juste avant
language_id -> saisi 
first_name -> saisi 
last_name -> saisi 
created_at
updated_at 


CHEMIN 1 : SI COMANY DU USER DEJA ENREGISTRE IL SELECITONNERA ET LE FRONT RENVERRA DIRCTEMENT L'ID
3) table companies_users : 
id automatique 
user_id -> liée à l'id generé sur la table "users"
company_id -> saisi 
created_at -> auto 
updated_at -> auto 

CHEMIN 2 : SI IL NE VOIT PAS SA COMPANY ENREGISTRÉ ALORS IL FAUT POUVOIR AJOUTÉ UNE COMPANY DONC ON REMPLIE LA TABLE : 
3) bis table companies: 
tva_intra_com -> saisi 
created_at -> auto 
is_verified -> plus tard 
updated_at -> auto 
company_name -> saisi 
phone_number -> saisi 
code_naf -> saisi 
email -> saisi 
condition_reglement -> saisi  
branche -> saisi 
extrait_kbis plus tard
cgv_accepted ->  True or False selon le json recu 
website -> saisi 
description -> saisi 
logo plus tard 
VAT_rate -> saisi 

4) table addresses : 
id -> auto 
zip_code -> saisi 
city -> saisi 
created_at
updated_at
type -> saisi 
street -> saisi 
state -> saisi 
country_code -> saisi 
lat -> plus tard  
lng -> plus tard  
is_primary -> plus tard 
company_id -> saisi 
siret -> saisi 

5) table companies_users : 
id automatique 
user_id -> liée à l'id generé sur la table "users"
company_id -> tva_intra_com saisi par le user (et qui devrait mtn exiter dans la table 'companies' comme PK)
created_at -> auto 
updated_at -> auto 

FIN DES CHEMIN DIFFERENTS. 

exemple de json qui sera renvoyé pour le moment : 

{
first_name -> saisi 
last_name -> saisi 
email : value
password_hash -> créer par le user vu qu'on est sur un login 
is_active : True  
role_id : 1
mobile_phone -> saisi 
fixe_phone -> saisi 
language_id -> saisi 
company_id -> numero_ TVA intra com 
tva_intra_com -> numero_ TVA intra com  
company_name -> saisi 
comapnie phone_number -> saisi 
code_naf -> saisi 
companie email -> saisi 
condition_reglement -> saisi  
branche -> saisi 
extrait_kbis : aucune idée du format actuellement 
cgv_accepted ->  True or False selon le json recu 
website -> saisi (surement une url )
description -> saisi 
logo : aucune idée du format actuellement 
VAT_rate -> saisi 
zip_code -> saisi 
city -> saisi 
type -> saisi 
street -> saisi 
state -> saisi 
country_code -> saisi 
lat -> plus tard  
lng -> plus tard  
is_primary -> true or false 
company_id -> tva_intra_com 
siret -> saisi 
company_id -> tva_intra_com saisi par le user (et qui devrait mtn exiter dans la table 'companies' comme PK)
}
voilà j'espere que ça peut aider tout ce qui est indiqué comme "saisi" : c'ets des string qui arrievront surement
}



DEMANDE 2: 
{
role : CLIENT
demande : Le client dois pouvoir créer un compte avec ses information necessaire a l'identification (c'est a dire tous les champs disponible sur les models de table postgre sql dispo dans le projet qui concerne l'identification du client) je veux pour une premiere etape une route dédier a la création d'un "compte" exclusivement pour les client donc le front renverra un json avec toutes les infos et la route doit feed la DB avec ces infos et verifier bien sur si les info de Primary key ne sont pas deja existante genre mail nom prenom etc etc. 
autre : quelques precision tu ne fais que le travail d'api et backend le front end avec les connection  a cette route est un autre sujet qui sera traiter. la route n'est que pour céer un nouveau compte forunisseur on traite pas les info client ou admin ici regarde bien comment est construite la DB dans le dossier /models pour faire les query correct 
}

DEMANDE 3: 
{
role : ADMIN
demande : Le client dois pouvoir créer un compte avec ses information necessaire a l'identification (c'est a dire tous les champs disponible sur les models de table postgre sql dispo dans le projet qui concerne l'identification du client) je veux pour une premiere etape une route dédier a la création d'un "compte" exclusivement pour les client donc le front renverra un json avec toutes les infos et la route doit feed la DB avec ces infos et verifier bien sur si les info de Primary key ne sont pas deja existante genre mail nom prenom etc etc. 
autre : quelques precision tu ne fais que le travail d'api et backend le front end avec les connection  a cette route est un autre sujet qui sera traiter. la route n'est que pour céer un nouveau compte forunisseur on traite pas les info client ou admin ici regarde bien comment est construite la DB dans le dossier /models pour faire les query correct 
}


DEMANDE 3: 
{
role : FOURNISSEUR
demande : Ajout d'item dans la DB liée au forunisseur, chaque foiurnisseur doit pouvoir référencer des nouveaux produits ou nouveau stocks de produit qu'il mettra a disposition sur notre platform. Pour cela il y aura une frontend avec des formulaire qui feront un appel à notre API dont il faut que tu me crée une route dédier pour filled la ou les tables concerné par les produits disponibles donc a partir d'un json il faudra que la DB soit remplie en fur et a mesure
autre :1. Il faut des test pour savoir si le produit existe deja ou si la categorie de produit existe deja au quel ca sil faudra update certaine data notament les stocks etc ça il faut que tu te refete au /models dispo dans le backend pour voir les champs, tables et connexions pour faire ces test logique. 
2. Si il n'y a pas deja le produit / la categorie de produits / ou tout autres specificité, alors on créer un nouvel item sur les tables concernés. 
3. test pour refusé l'ajout de produit si il manque des info important tel que des catégroire de produti sous categorie ou autre (selon ce qui existe dans la DB bien sur). 
}

DEMANDE 4: 
{
role : FOURNISSEUR
demande : Delete d'item dans la DB liée au forunisseur, chaque foiurnisseur doit pouvoir effacer des produits qu'il ne mettra plus à disposition sur notre platform. Pour cela il y aura un frontend avec des formulaire qui feront un appel à notre API dont il faut que tu me crée une route dédier pour fouiller la ou les tables concerné par les produits disponibles donc a partir d'un json, il faudra pouvoir effacer certian produit.
autre :1. Il faut des test pour savoir si le produit existe deja 

}

DEMANDE 5: 
{
role : FOURNISSEUR
demande : modification d'item dans la DB liée au forunisseur, chaque foiurnisseur doit pouvoir modifier des produits qu'il  mettra  à disposition sur notre platform. Pour cela il y aura un frontend avec des formulaire qui feront un appel à notre API dont il faut que tu me crée une route dédier pour fouiller la ou les tables concerné par les produits disponibles donc a partir d'un json, il faudra pouvoir modifier certain champs du produit. donc bien definir les query etc parce qu'on veut pas modifier des caracteristique qui en ferai un nouveau produit dans l'absolue. 
autre : 1. Il faut des test pour savoir si le produit existe deja 
2. Si il n'existe aps alors il faudra le créer MAIS ce n'est aps le role de cette demande donc la route api ne doit pas en créer de nouvelle juste mdoofier donc err si inexistant
3. Les modifications ne peuvent se faire que sur des champs précis comme la uptdate_at, currency, le references prices par exemple mais jamais l'ID ni le product type. si le product type est mauvais il delete et créer un nouvel item
}



ajouter dans la table : orders 
 - seller --> liée à la primarikey de "users"
 - buyer --> liée à la primarikey de "users"



DEMANDE 3: 
{
role : FOURNISSEUR
demande : Le forunisseur dois pouvoir enregistrer ses prduit a vendre car la finalité c'ets une platforme marchande de bien ets ervice. Pour ça c'ets répartie en plusieurs couche on retrouvera d'abord la le type de service avec une table dedié, on associé aussi un catalogs qui sera liée a un catalog d'item qui lui sera liée à la fois au produit de la table products qui aura des dependances avec des attribut speciaux sur la table product-attribut et price history. et surtout catalog item est aussi liée à la table company_catalog_items. très important car c'est elle qui va referencé les prix currency etc. donc ça c'ets une mission qui va etre decoupé en plusieru route api qui se succederont. aussi la table shipping rate a remlir pour sa boite. 



route 1 : shipping : 

pour un user liée a une boite il doit simplement pouvoir remplir la table : 

table shipping_rates : 

id - > auto 
carrier_name -> saisi 
zone_from  -> saisi 
zone_to  -> saisi 
weight_min_kg  -> saisi 
weight_max_kg -> saisi 
volume_max_m3 -> saisi 
rate_per_kg -> saisi 
base_rate -> saisi 
currency -> saisi 
is_active True 
created_at auto 
updated_at auto 
company_id  -> saisi 

route 2 : services pour la prmeiere fois : 
1) table  : services
id
reference_price -> saisi 
currency -> saisi 
duration_unit -> saisi 
duration_value -> saisi 
remote_available -> true or false  
is_active ture false 
created_at
updated_at
company_id -> liée au tva intra com de comapnies à laquelle ets rataché le user en question  
service_type -> saisi 

2) table : catalogs 

id
name -> saisi 
description -> saisi 
is_active
created_at
updated_at
company_id -> tvaintracom (PK table companies)  
parent_id -> auto referece si jamais sous catalog on reverra ça plus tard

3) table catalog_items : 
id
catalog_id -> liée à l'id crée juste avant à la table catalogs  
created_at
updated_at
service_id -> liée à l'id crée juste avant à la table services


4) table : company_catalog_items : 
id
company_id -> tva intracom 
catalog_item_id -> id associé à la table catalog items qui a été crée
custom_price -> saisi 
currency -> saisi 
stock_quantity -> saisi 
is_available true flase 
created_at
updated_at


5) table products : 
id
sku 
created_at
updated_at
product_type
reference_price -> liée à company_catalog_items.custom_price 
currency -> liée à company_catalog_items.currency  
is_active
catalog_item_id -> id associé à la table catalog items associé 
companies_id -> tva_intracom du user qui feed
teinte
type_de_produit
gamme
duree_garantie
conditions_garantie
piece_ouvrage_destination
traitement_bois_classification
produit_nuance
description_profil
couleur_traitement_autoclave
code_douane_sh8
type_bois
essence_bois
longueur
largeur
hauteur
volume
poids_net


route 3 : lorsque qu'un company a deja un servcie et qu'elel veut pas en recréer un autre, alors elle se connectera sur un page dedier ou elle sera deja sur son service avec ses info apr contre elle a la possibilité de créer un nouveau catalog item et tout ce qui en decoule avec le company_catalog_item et la table products etc etc donc comme laroute precedente mais on vient au milieud e la chaine et donc on récupérer les meme variable commeune de la companie et du service etc 


Route 4 : on doit pouvoir venir modifier directement le stock_quantity currency et custom_price sur la table company_catalog_items à partir du company_id et catalog_item_id. 

Route 5 : idem que route 4 mais pour modifier les champs de la table products à partir d'un comapny id et catalog_item_id 




autre : voici dans l'ordre il faut traiter les champs et les tables qui devront etre remplie atention il y a u split selon si la company existe deja ou non : 

1) table : users
id -> automatique 
email -> saisi par le user 
password_hash -> créer par le user vu qu'on est sur un login 
is_active -> par default = True 
created_at -> automatique des time stamp de cration 
updated_at -> automatique des time stamp des que y a un update  
role_id -> role id vu qu'on est sur la creation du compte fournisseur ce sera toujours 1 sur cette requete. Car le role etant fournisseur et l'id role correspondant est le 1. 
mobile_phone -> saisi 
fixe_phone -> saisi 

2) table user_profiles : 
id 
user_id -> liée à l'id generé sur la table "users" juste avant
language_id -> saisi 
first_name -> saisi 
last_name -> saisi 
created_at
updated_at 


CHEMIN 1 : SI COMANY DU USER DEJA ENREGISTRE IL SELECITONNERA ET LE FRONT RENVERRA DIRCTEMENT L'ID
3) table companies_users : 
id automatique 
user_id -> liée à l'id generé sur la table "users"
company_id -> saisi 
created_at -> auto 
updated_at -> auto 

CHEMIN 2 : SI IL NE VOIT PAS SA COMPANY ENREGISTRÉ ALORS IL FAUT POUVOIR AJOUTÉ UNE COMPANY DONC ON REMPLIE LA TABLE : 
3) bis table companies: 
tva_intra_com -> saisi 
created_at -> auto 
is_verified -> plus tard 
updated_at -> auto 
company_name -> saisi 
phone_number -> saisi 
code_naf -> saisi 
email -> saisi 
condition_reglement -> saisi  
branche -> saisi 
extrait_kbis plus tard
cgv_accepted ->  True or False selon le json recu 
website -> saisi 
description -> saisi 
logo plus tard 
VAT_rate -> saisi 

4) table addresses : 
id -> auto 
zip_code -> saisi 
city -> saisi 
created_at
updated_at
type -> saisi 
street -> saisi 
state -> saisi 
country_code -> saisi 
lat -> plus tard  
lng -> plus tard  
is_primary -> plus tard 
company_id -> saisi 
siret -> saisi 

5) table companies_users : 
id automatique 
user_id -> liée à l'id generé sur la table "users"
company_id -> tva_intra_com saisi par le user (et qui devrait mtn exiter dans la table 'companies' comme PK)
created_at -> auto 
updated_at -> auto 

FIN DES CHEMIN DIFFERENTS. 

exemple de json qui sera renvoyé pour le moment : 

{
first_name -> saisi 
last_name -> saisi 
email : value
password_hash -> créer par le user vu qu'on est sur un login 
is_active : True  
role_id : 1
mobile_phone -> saisi 
fixe_phone -> saisi 
language_id -> saisi 
company_id -> numero_ TVA intra com 
tva_intra_com -> numero_ TVA intra com  
company_name -> saisi 
comapnie phone_number -> saisi 
code_naf -> saisi 
companie email -> saisi 
condition_reglement -> saisi  
branche -> saisi 
extrait_kbis : aucune idée du format actuellement 
cgv_accepted ->  True or False selon le json recu 
website -> saisi (surement une url )
description -> saisi 
logo : aucune idée du format actuellement 
VAT_rate -> saisi 
zip_code -> saisi 
city -> saisi 
type -> saisi 
street -> saisi 
state -> saisi 
country_code -> saisi 
lat -> plus tard  
lng -> plus tard  
is_primary -> true or false 
company_id -> tva_intra_com 
siret -> saisi 
company_id -> tva_intra_com saisi par le user (et qui devrait mtn exiter dans la table 'companies' comme PK)
}
voilà j'espere que ça peut aider tout ce qui est indiqué comme "saisi" : c'ets des string qui arrievront surement
}



tu vas me m'aider à créer tous mes



















ok derniere features a ajouter les produits par companies. 

Il faut que :

- à partir des user profils qui ont été créer et liée à une companie en tant que fourisseur, un fournisseur doit avori une interface sur le site qui lui permette d'ajouter un service/catalog/produits 


- la DB est faite ainsi : le user qui ets liée à un ecompany basé sur la table companies_users, va permettre d'arriver a la table qu'on a remplie en dernier qui est : companies qu'on a remplie avec les infos minimum 

- notre mission maintenant c'est que tu vas créer un button sur la bandeau header sur l'interface, uniquement si le user session est un role de fournisseur, d'ailleur quand on ets connecté en tant que fournissuer il faut qu'on créer une nouvelle page d'accuil celle qu'on a c'ets celle quand on est aps encore connecté des qu'on est connecté tu me crée une page simple avec 3 choix sur la page : 

1) update / create services 
2) shipping methode 
3) payement info 

On va faire chaque arborescence en commençant par la fonctionnalité  1) :


quand on clique sur 1) il faut à chaque table avoir une page dédier de choix donc dans l'ordre on va traiter la table 

a. Service  
b. catalogs
c. ctaalogs_item
d. Products 
e. product_attribut
f. Company_catalog_items

Donc on a jusqu'à 5 étapes. Car c'ets soit on ajoute un nouveua produit dans ce cas la on ira jusqu'à l'étape 5, soit on modifie un sevrice un catalog un produit ou un attribu d eproduit au quel cas bah on ira aussi profond que necessiare pour la modife on sauvegarde et c'est tout. Sur le principe c'est simple. 


Donc quand on clique sur le menu 1) : 

a. en arrivant connecté en tant que fournisseur il faut que tu me fasse une premeire page ou le user à le choix entre : créer un nouveau service ou accéder à un service déjà existant liée à sa companies dans la DB.
Si on créer un nouveau service il faut pouvoir remplir toutes ces infos : 

pour la table services c'est obligatoire de remplir les champs : 
"is active" oui ou non choisi par le user pour savoir si bah le service est dispo ou pas  
"service_type" , sahcnat que c'ets soit quelque chose que le user écrit soit il peut choisir un type de service deja existant dans tous les services type de la DB dans la table services. 

le reste est aps obligatoire mais il fuat pouvoir le mettre dans des settings avancé : 
reference_price
currency
duration_unit
duration_value
remote_available


si il vient juste modifier un service il faut juste la liste deroulante des service enregistré (on liste les service type pas les id de service bien sur). une fois que le sevrice est choisi on affiche les meme setting sur l'interface que si on créait un service sauf que tt est pré remplie avec ce qui est enregistré dans la DB logique). 

ensuite et ce pour chaque page : il faut un boutton suivant qui menne à la prochaine etape sur les 5, ou un boutton enregistré si il décide de s'arreter la pour reprendre plus tard ou juste parce qu'il est venu pour modifier des trucs et rien de plus. 

b. Si il clique sur suivant alors on passe à la deuxieme page qui lui permet d'accéder sur la meme logique pour la table catalogs, si il avait chosisi au début de modifier ou de créer un nouveau service ici il a encore le choix de créer ou modifier elle sont indépendante. donc listing des ctaalogs existant ou création d'un catalogs en remplissant obligatoirement : 
name
description
is_active booléen de savoir si le catalog est dispo ou pas 

si il veut modifier des truc bah il modifira les meme champs qui seront pré remplie avec ce qu'il y a dans la DB. 
aussi quand on crée un catalogs il y a une etape obligatoire en plus qui est le "parent_id" en gros c'ets pour des sosu catalogs par exemple il fait un ctaalog de caisselle il y aura un sous catalogs de couvert un sous catalog d'assiette un sous ctalog de verre etc. 
Donc quand on crée un catalog il faut choisir pour le parent_id genre à quel catalog on lie le catalogs qu'on crée, et ça peut etre aucun donc crée rune sorte de premiere catalogs, dans ce cas la le parents id c'ets l'id meme du catalogs. Sinon il peut choisir parmis de liée son catalogs basé sur un  ctaalogs deja presentd ans la DB a partir d'une liste deroulante de ctaalogs.name liée à sa company_id du user. 
et le parent_id sera le catalogs.id du catalogs donc le nom a été selectionné. 

enregistré ou suivant 

c. une fois qu'il clique sur suivant et qu'il a traité service et catalogs, alors il va pouvoir liée un service avec un catalogs, il doit pouvoir fair n'importe lequel entre eux liée à sa companies. Il faut que si un catalogs a été créer le catalogs nouveau soit préremplie dans la liste des catalogs a lier, meme principe pour le service si un service a été créer il ser apré remplie dans la liste deroulante des service a liée a un catalogs. 
On commence toujours par donner le services dans une liste deroulante ou on voit tous les services de la boites et pré remplie avec le denrier service créer enft vu qu'on a un update_at dans la db. puis on doit voir un tableau avec tt les catalagos liée à ce services (table catalog_item) et on a la possibilité de drop un ctaalog a la volé pour enleve un catalog du service selectionné, mais il faut aussi une barre de recherche qui permet de selection trouvé cherche n'importe quel catalogs de la company liée au user et juste bah ça l'ajoute au table et donc il faudra liée avec une ligne en plus dans la table ctaalog_items en remplissant automatiquement catalog_id et service_id selon la liste d catalog liée au service sur l'interface. Attention pas de doublon donc on verifie si la pair n'existe aps deja dans la DB catalog_item entre le service id et le catalogs id. On ajoute les ligne qui n'existe pas seulement.

enregistré ou continuer

d. u fois qu'on continue après avoir liée service et catalog, dans catalog item, on va remplire la table de products, cette table et directement liée à ctaalog_items donc o aura bien un ctaalog qui peut etre enfant ou parents d'autre catalogs qui liée a un service aura aussi une pluralité de product lié a son catalogs item. Pour cette page encore une fois soit on modiife soit on crée, si on modifie meme principe on vinet selectionner dans une liste déroulante un product liée au catalog_itms qu'on a créer ou selectionné à l'étape précédente, et on pré remplie tt les champs dispo : 

sku obligatoire 
product_type obligatoire
reference_price obligatoire
is_active obligatoire
teinte
gamme
duree_garantie 
conditions_garantie
piece_ouvrage_destination
traitement_bois_classification
produit_nuance
description_profil
couleur_traitement_autoclave
type_bois
longueur
hauteur
largeur
volume  obligatoire
poids_net  obligatoire

ur product voici ce qui doit etre obligatoire ou non ce qui est obligatoire apprait direct ce qu'il ne l'est pas comme d'hb on fait un boutton avec otpion avancé et on fiat apparaitre le reste et on remplie la db. 

enrgistrer ou suivant. 

e. alors soit sur la meme page que product avec une option pour ajouter un attribu specifique qui ouvrirait un pop up simple qui va venir ajoute dans la table product_attribut liée au product id qu'on modifie ou qu'on vient de créer (lui meme liée à un ctaalogs item lien par service et par catalogs à companies) : 
-name
- value
et on peut en faire autant qu'on veut il suffit d'enregistrer le pop up disparait et la db et feedé, et on reclique sur ajouter un attirbut specifique, il faut donc dan sle pp up listé les attribut specifique deja liée au produit en question et pouvoir les supprimés un par un. 

enregistrer ou suivant  je ense que d. et e. c'ets bien de les avoirs ensembles sur la meem page en vria le pop up pour e. c'ets tres bien


f. derniere etape une derniere page ou on précise le prix dans la table liée au catalogs item, dans la table companies_catalog_items : tout est obligatoire dans cette table. 

-custom_price
-currency
-stock_quantity
-is_available

bien sur c'ets soit on modiife parce qu'on est venu chercher un produit deja existant ou on a crée un produit donc on vient créer la base les 4 bloc a remplir appraisse tt le temps il sont obligatoire pas d'option caché etc stp.

button terminer retour à l'écran principal pour un rôle session de fournisseur. 


voilà si tu arrive a me faire ça en respectant lUI UX comme tu l'a fait juste que la, pense a implementer le fait qu'on doit etre adaptable sur ordi table et smartphone et donc que les pop up et les page sont scrollable pour aller voir tt les settings etc stp. 


c'ets important que tt soit cohernet visuellement aussi mais surotu que la db se feed corretcement !!! 






Pour le parcours de shipping rates : 

direct il faut savoir dans quel parcours on se place : 

soit on ajoute un shipping rate soit on modifie mais pas un switch en plein milieu stp la c'ets vrmt soit l'un soit l'autre et ça rest ecomme ça tant qu'on est pas allé au bout. 

Pour create un shipping rates : simplement une 1ere page qui demande de quel depart à quel arrivé concerne le shipping rate qui est créé. Donc prmeiere page on remplie les zone zone_from, zone_to, carrier_name et is active (tout est obligatoire). Deuxieme page 
-weight_min_kg
-weight_max_kg
-volume_max_m3
-rate_per_kg
-base_rate
-currency

et c'est fini c'est tres simple donc création ou acces pour modifier et enregistrement à la fin. 


Pour le parcours company methode de payement meme delire on vient feed company_payment_methods sur une prmeiere page soit on crée un nouvelle methode soit on modifie une methode. 

Il faut remplir tt ça obligatoirement : methode qui est une saisi pour le moment. 
puis enregistrer ou suivant et la deuxieme page il faut remplir simplement cette data : 

- iban_number
- bic
- bank_name
- is_primary
