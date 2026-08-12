
On va tous clean sans regarder ce qu'il y a dedans je vais t'expliquer la manière dont tu vas devoir créer un model ou je peux drag and drop un csv come celui dans OLD_DATA qui aura toujours a minima les colonnes du csv qui sont les suivantes 

[Référence,	Nom commercial,	Description, Prix référence HT, Unité, Urbyn, Nb de massif / palette, Passage Fourche,	"Manille
Nombre",	Manille Type,	Hauteur mât (maximale) en m, Largeur,	Longueur,	Hauteur	Poids(kg), 	Volume (m3),	Fournisseur]


il faudra intégrer dans la gestion de catalog un truc pour faire de l'implémentation 'gros volume donc par des fichier csv formatté justement, qui permette de drag and drop le csv et ça interge les produit dans les ctaalog et créer au besoin tous les catalogs necessaire. 

Il faut aussi prévoir si c'est une intégration additive = on ajoute les produit au catalog si il existe deja et on crée les catalog manquant si jamais 
Ou si c'est une intégration destructive = si il y a des catalogs manquant alors on les crées normal mais is il u a des produti a mettre dans des catalog existant on vide les catalogues existants et on ne met qu eles produits du fichier qui arrive. 


mtn que ça c'est fait/dis, voilà comment il faut remplir la DB systematiquement selon les infos du csv : 

Nom commercial == products.product_name
Référence==products.client_sku 
Description== un attribu obligatoire de descirption ou une section descirption qui est surement deja présente dans la DB ou l'interface jsp en tt cas tu sauras ou le mettre 
Prix référence HT==product_price_history.price 
Unité== product_price_history.currency
Urbyn==: hyper important de comprendre la structure c'est ici qu'on crée ou place dans les différents catalogs où doivent se retrouver chaque produit. Donc la logique est super simple à chaque [] ça représnete un catalog fille dans lequel le produit dois appraitre. et a l'intérieur de chauqe [] est décrite le file d'arianne du catalog racine au catalog fille qui contient le produit en question. Docn si un ctaalog n'existe pas que ce soit a la racine ou n intermediaire ou le ctaalog fille on le crée et si il existe deja on l'exploite c'ets t gnere on pass epar lui ou on place le produit dedans selon sa place dans le chemin. 

exempel : 
un produti TEST contient ça : 
"[Lestage/3700 kg]
[Massif_Moyen_de_Levage/Manille]
[Massif_Moyen_de_Levage/Fourche]
[Massif_Type/Temporaire/Cubique]
[Massif_Typology/Entraxe/300x300]"
alors il appariat dans 5 catalogs diffenrets qui ont chacun leur arboresncnces. 

ENSUITE TOUS LES CHAMPS QUI SONT APRÈS LE CHAMPS "Urbyn" SONT DES ATTRIBUT QU'IL FAUT AJOUTER DYNAMIQUEMENT avec le nom du champs== .name de l'attribu et valeur == bah la valeur associé au champs pour chaque lignes produits. 

voilà c'ets pas plus compliqé que ça. 

sachnatque ici pour ce csv c'ets une premiere donc il est aps encore super clean mais si y a un nom de produit on crée si il manque une reference pour le sku tu génère le sku aléatoirement avec  des lettre majuscule. 

et voilà normalemnt t'as tout pour me crer les routes api le backend et l'interface dans l'admin pour intégrer tout ça !

Aussi un truc qui me plaisria c'est quea travers les catalogs la notion d'attrbut bligatoire elle me plait  plus trop je crois donc si possible faire en sorte d'afficher la lisye des attribut qui existe sur les produit d'un catalog soit jsute listé ar defaut il ssont en facultatif et juste un boutton switch les rends obligatoire ou non et donc ça changera des truc pour l'affichage d'un produit coté client mais ça on verra plsu tard deja ce systeme de swithc simplke d'un catalog a l'autre pour rendre un truc obligatoire ou non stp 