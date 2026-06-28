Ok voici un projet sur la dev d'une  platfrome. 

La on a actuellemnt une base d eoné un backend python qui tourne avec lien postgreSQL grace a alembic et tt nos model de route api etc etc dans le backend dans le front end on a mis en place tt la logique de connexion et de gestion de ctalog de produit coté fournisseur et gestion de la BD avec tt ça aussi la page independnate d'admine est aussi bien foncitonnel avec la gestion des user company etc etc c'est tt foncitonnel mais le principe d'une platfeforme c'ets de rasembler 2 tipologie de client donc dans cette logique on va venir créer tt la partie "user" qui sera beaucoup moins lourde que la partie fournisseur car les forunisseur etait directemnt en lien avec le feeding des produit donc c'était très structurant toi ton role en tant qu'agent sera exclusivement de gérer la definition de nouvelle route API avec la DB ou pour du calcul ou autre tu t'occupera aussi de gérer tt l'inteerface de création de nouveau module a des page entiere à l'UI UX en respectant ce qui est deja en place. 

ça sera plus simple de faire back et front au meme endroit. 

Tu peux lire tt les models et autre fichier dispo dans l'arborescnece sans aucun restriction mais INTERDICTION de toucher au model alembic et tt ce qui est lien avec les fichier/dossier de DB Neon interdit tu les exploite juste tu fais des imports comme tu veux mais aucune modif. 

Voilà pour le contexte et delimitation de role. 

1eme misison tu vas me répliquer le comportement de connexion pour la création et connexion à l'interface coté client/acheteur ok ?

regarde les champs la menier edont c'est feedé coté neon et normalemnt c'est exactement pareil avec les acheteur car les achteur sont aussi liée à une entre prise etc etc et l'entreprise peut etre et donc juste on recupere de la meme maniere les meme information d'un coté et de l'autre une fois quo'n est conecter on va voir comment on gère les referencement de produit pour la recherche intelligente au produit par produit ensuite on verra pour les produti composit et enfin gestion des panier et des historique d'order order etec etc etc pour pouvoir faire ensuite tt la partie dashboarding pour tt les partie acheteur / fournisseur / admin ok