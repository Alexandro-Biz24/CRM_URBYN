à partir de l'environnement potsgreSQl dans lequel tu es est deja on va refaire une bonne partie de la DB niveau architecture. 

Voici comment va se comporter les tables, certain seront supprimé et d'autre seront modifier. 


dans l'idée pour créer quelque chose de cohérent, mtn ça sera les catalogue qui sont centraux à la DB et plus les companies. 


ce qu'il me faut : 

1) les tables inchangé : 
-roles
-users
-typologie
-reviews
-email_verification_codes
-languages
-user_profiles
-review_translations
-companies_users
-companies
-addresses
-shipping_rates
-companies_bank_info
-company_payment_methods


Donc les inchangés, on n'y touche pas pour le moment elle ne doivent pas changé dans leur fonciton, après c'est tout a fait possible que certain champs soit a adapter si il y a suppréssion de table qui était linked c'ets possible

2)  les tables qui sont supprimées : 
- services
- catalog_items
- company_catalog_items

donc pour chaque table supprimé il fuat penser a supprimer les lien avec les autres tableau voici la liste : 

pour service {service_translations.service_id / product_order.service_id / pour le lien avec catalog_items la table est supprimé aussi donc c'est aps grave}

3) les tables modifiées/adapté :

-products
-catalogs
-product_price_history
-product_order

les modification à faire par table : 

3.1) products: 
    ADMIN_SKU                       :   NEW
    catalog_ref                     :   NEW (id d'un catalog de la table (catalogs))
    Client_sku                      :   RENAMED FORM "sku"
    created_at                      :   STILL
    updated_at                      :   STILL
    product_type                    :   STILL
    reference_price                 :   SUPPR
    currency                        :   SUPPR
    is_active                       :   STILL
    catalog_item_id                 :   SUPPR
    companies_id                    :   STILL
    quantity                        :   NEW
    teinte                          :   STILL
    type_de_produit                 :   STILL
    gamme                           :   STILL
    duree_garantie                  :   STILL
    conditions_garantie             :   STILL
    piece_ouvrage_destination       :   STILL
    traitement_bois_classification  :   STILL
    produit_nuance                  :   STILL
    description_profil              :   STILL
    couleur_traitement_autoclave    :   STILL
    code_douane_sh8                 :   STILL
    type_bois                       :   STILL
    essence_bois                    :   STILL
    longueur                        :   STILL
    largeur                         :   STILL
    hauteur                         :   STILL
    volume                          :   STILL
    poids_net                       :   STILL

3.2) catalogs: 
    
    name            : STILL
    description     : STILL
    is_active       : STILL
    created_at      : STILL
    updated_at      : STILL
    company_id      : SUPPR
    parent_id       : STILL

3.3) product_price_history: ça doit devenir une time series je sais pas trop comment faire là  

    date            : NEW
    product_id      : STILL
    price           : STILL
    currency        : STILL
    effective_at    : SUPPR
    created_at      : STILL

mais il faut qu'à chaque fois qu'on vienne modifier le prix pour un produit identifié, alors on ajoute automatiquement une ligne dans cette table avec la date current et les info de price product_id concerné et currency 

Comme ça quand on vient requeeter on preux prendr ecurrency price avec la last date ou date plu srecente de chaque product ID et on peut mme faire des stats sur les historiques de prix de chaque produit tu vois ce que je veux dire ? tu peux me faire des proposition d'architecture pour cette partie si tu as une idée. 

3.4) product_order

order_id        : STILL
catalog_id      : NEW   
product_id      : STILL
service_id      : SUPPR
item_type       : SUPPR
quantity        : STILL
unit_price      : STILL
shipping_cost   : STILL
total_price     : STILL
created_at      : STILL
updated_at      : STILL
