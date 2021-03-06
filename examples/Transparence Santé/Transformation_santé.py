
# coding: utf-8

#!/usr/bin/env python


"""
A partir des fonctions du dépôt anonymizer, ce fichier va notamment vous permettre de :

1. **Importer** les données de la base Transparence Santé.
2. **Nettoyer** les variables et sélectionner celles à anonymiser
3. **Anonymiser** les données selon un procédé de K-anonymisation
4. **Compléter** avec les données INSEE afin d'en mesurer la plus-value.


The file can be downloaded here:
https://www.data.gouv.fr/fr/datasets/transparence-sante-1/
or directly :
https://www.transparence.sante.gouv.fr/exports-etalab/exports-etalab.zip

Le jeu de données contient environ 2 millions de lignes. Le fichier exports-etalab.zip contient :

    Le jeu de données
    La présentation du jeu de données
    La licence d’utilisation du jeu de données    
  
  
  
Le fichier INSEE pour l'enrichissement des données peut être téléchargé ici :
http://www.insee.fr/fr/themes/detail.asp?reg_id=99&ref_id=equip-serv-medical-para
or directly
http://www.insee.fr/fr/ppp/bases-de-donnees/donnees-detaillees/equip-serv-medical-para/equip-serv-medical-para-com-2015.zip

"""

import csv
import numpy as np
import pandas as pd
import matplotlib
import matplotlib.pyplot as plt

from import_insee import (expand_insee, nbre_modif)

from anonymizer.anonymity import (get_k, get_anonymities,
                                  less_anonym_groups,
                                  all_local_aggregation,
                                  )
from anonymizer.diversity import (get_l,
                                  get_diversities,
                                  diversity_distribution,
                                  less_diverse_groups
                                )
from anonymizer.transformations import (first_letters,
                                       last_letters)
from anonymizer.transformations import str_drop
from anonymizer.anonymDF import AnonymDataFrame

from anonymizer.config_anonymizer import config
import os
import io


# ## I. Nettoyage de la base de données

# Importation des 50 000 premières lignes

path_data = config['PATH']['TRANSPARENCE']

nbre_lignes = 50000
avantages = pd.read_csv(path_data, sep = ";", nrows = nbre_lignes, low_memory = False)



# === Séparation personnes physiques/morales ===

# On ne traite pas le cas des personnes morales


code_personne_physique = ['[PRS]','[ETU]']
personnes_physiques = avantages[avantages['benef_categorie_code'].isin(code_personne_physique)]
personnes_morales = avantages[~avantages['benef_categorie_code'].isin(code_personne_physique)]
avantages = personnes_physiques

xxx

# === transformations préalables ===

# * On transforme les CP en indicateurs régionaux
avantages['benef_dept'] = first_letters(avantages['benef_codepostal'],2)

# * On supprime les CP peu orthodoxes
erreur_CP = ['0', '', 'IN']
avantages.loc[avantages['benef_dept'].isin(erreur_CP), 'benef_dept'] = np.nan
erreur_pays = ['[RE]','[GP]']
avantages.loc[avantages['benef_pays_code'].isin(erreur_pays), 'benef_pays_code'] = '[FR]'

# * On homogénéise les valeurs manquantes ou tierces par la mention "non-renseigné"
avantages = avantages.fillna('non renseigné')
to_replace = ['[AUTRE]', '']
avantages.replace(to_replace, 'non renseigné', inplace=True)

# * On transforme la valeur des conventions/avantages en leur équivalent décile (uniformisation)

avantages['avant_montant_ttc'] = avantages['avant_montant_ttc'].astype(float)
avantages['montant_décile'] = pd.qcut(avantages.avant_montant_ttc,10)

# * On transforme la date (signature des avantages) en mois/année (le jour est trop identifiant)

avantages['date'] = last_letters(avantages['avant_date_signature'],3)

avantages['avant_nature'] = avantages['avant_nature'].str.lower()


# * On supprime d'abord les variables identifiantes afin de ne garder que les variables quasi-identifiantes

variables_supprimees = ['avant_convention_lie',
                        'identifiant_type',
                        'benef_qualification',
                        'benef_speicalite_libelle',
                        'ligne_rectification',
                        'denomination_sociale',
                        'benef_titre_libelle',
                        'benef_prenom',
                        'benef_nom',
                        'benef_adresse1',
                        'benef_adresse2',
                        'benef_adresse3',
                        'benef_adresse4',
                        'benef_identifiant_valeur',
                        'benef_ville',
                        'benef_etablissement_ville',
                        'categorie',
                        'benef_qualite_code',
                        'benef_codepostal',
                        'benef_etablissement_codepostal',
                       'ligne_identifiant',
                       'pays',
                       'benef_denomination_sociale',
                       'benef_objet_social',
                        'avant_date_signature',
                        'avant_montant_ttc',
                       'benef_etablissement']

avantages = avantages.drop(variables_supprimees,1)

avantages['montant_décile'] = avantages['montant_décile'].astype(str)
avantages['date'] = avantages['date'].astype(str)



# On définit ici les variables traitées pour l'anonymisation

var = avantages.columns.tolist()
var.remove('ligne_type')
var.remove('avant_nature')



# ## II. Traitement des données brutes (sans INSEE)

# On k-anonymise dès maintenant la base brute.
# On définit ici k = 5

ordre_aggregation = ['benef_dept',
        'benef_categorie_code',
        'qualite',
        'benef_pays_code',
        'benef_titre_code',
        'benef_identifiant_type_code']

Avantages = AnonymDataFrame(avantages.copy(),  ordre_aggregation, unknown='non renseigné')
k = 5

def aggregation_serie(x):
    return(local_aggregation(x, k, 'regroup_with_smallest', 'non renseigné'))

def aggregation_year(x):
    return(local_aggregation(x, k, 'with_closest', 'non renseigné'))
    
method_anonymisation = [(name, aggregation_serie) for name in ordre_aggregation[:-1]] + [('date', aggregation_year)]

Avantages.local_transform(method_anonymisation, k)

modalites_modifiees = (Avantages.anonymized_df.values != avantages.values).sum()
modalites_intactes = (Avantages.anonymized_df.values == avantages.values).sum()



# ## II. Chargement des données INSEE

# construction d'un dictionnaire reliant les professions (INSEE) aux professions (Transparence Santé)

annuaire = {'Médecin omnipraticien' : ['benef_specialite_code', '[SM54]'],
 'Spécialiste en cardiologie' : ['benef_specialite_code', '[SM04]'],
 'Spécialiste en dermatologie vénéréologie' : ['benef_specialite_code', '[SM15]'],
 'Spécialiste en gynécologie médicale' : ['benef_specialite_code', '[SM19]'],
 'Spécialiste en gynécologie obstétrique' : ['benef_specialite_code', '[SM20]'],
 'Spécialiste en gastro-entérologie hépatologie' : ['benef_specialite_code', '[SM24]'],
 'Spécialiste en psychiatrie' : ['benef_specialite_code', '[SM42]'],
 'Spécialiste en ophtalmologie' : ['benef_specialite_code', '[SM38]'],
 'Spécialiste en oto-rhino-laryngologie' : ['benef_specialite_code', '[SM39]'],
 'Spécialiste en pédiatrie' : ['benef_specialite_code', '[SM40]'],
 'Spécialiste en pneumologie' : ['benef_specialite_code', '[SM41]'],
 'Spécialiste en radiodiagnostic et imagerie médicale' : ['benef_specialite_code', '[SM44]'],
 'Spécialiste en stomatologie' : ['benef_specialite_code', '[SM50]'],
 'Chirurgien dentiste' : ['qualite', 'Chirurgien-dentiste'],
 'Sage-femme' : ['qualite', 'Sage-femme'],
 'Infirmier' : ['qualite', 'Infirmier'],
 'Masseur kinésithérapeute' : ['qualite', 'Masseur-kinésithérapeute'],
 'Orthophoniste' : ['qualite', 'Orthophoniste'],
 'Orthoptiste' : ['qualite', 'Orthoptiste'],
 'Pédicure-podologue' : ['qualite', 'Pédicure-podologue'],
 'Audio prothésiste' : ['qualite', 'Audio prothésiste'],
 'Ergothérapeute' : ['qualite', 'Ergothérapeute'],
 'Psychomotricien' : ['qualite', 'Psychomotricien']}


# On charge les données INSEE

path_data_insee = config['PATH']['INSEE']

names = pd.read_excel(path_data_insee, encoding = "ISO-8859-1", skiprows=4, skip_footer=36000).columns
insee_init = pd.read_excel(path_data_insee, encoding = "ISO-8859-1", skiprows=5, headers=None, names=names)


insee_init['Département'] = insee_init['Département'].astype(str)
insee_init['Région 2016'] = insee_init['Région 2016'].astype(str)

insee_init['Département'] = first_letters(insee_init['Département'],2)




# On fusionne les départements d'Outre-mer dans une seule catégorie (trop identifiant, sinon)

outremer = ['1','2','3','4','6']
insee_init.loc[insee_init['Région 2016'].isin(outremer), 'Région 2016'] = 1

list_région = insee_init['Région 2016'].unique().tolist()

insee = insee_init.copy()

var_écartées = ['Région', 'Région 2016', 'CODGEO', 'Libellé commune ou ARM']
insee = insee.drop(var_écartées,1)



# === On rajoute à la base originale les données INSEE ===

# avantages_total est donc constituée de la base Transparence Santé, complétée par les données INSEE

g = insee.groupby('Département')

expanded_insee = expand_insee(g, annuaire, avantages)

expanded_insee.columns = avantages.columns.tolist()
avantages_total = pd.concat([avantages, expanded_insee]).reset_index()
avantages_total = avantages_total.drop('index',1)




# === On anonymise (données enrichies) ===


Avantages_avec_insee = AnonymDataFrame(avantages_total.copy(),  ordre_aggregation, unknown='non renseigné')

Avantages_avec_insee.local_transform(method_anonymisation, k, force_unknown='Forcer')
Avantages_avec_insee.df = Avantages_avec_insee.anonymized_df



table = Avantages_avec_insee.df[Avantages_avec_insee.df['ligne_type']=='[A]']
modalites_modifiees_avec_insee = (table.values != avantages_total[avantages_total['ligne_type']=='[A]'].values).sum()
modalites_intactes_avec_insee = (table.values == avantages_total[avantages_total['ligne_type']=='[A]'].values).sum()

## IV. Comparaison


# === On va maintenant comparer par variables le taux de remplacement ===

(avantages_kanonym[var[0]] != avantages[var[0]]).sum()

modif_par_var_1 = []
for variable in var :
    modif_par_var_1.append((avantages_kanonym[variable] != avantages[variable]).sum())

modif_par_var_2 = []
for variable in var :
    modif_par_var_2.append((result_insee[variable][result_insee['ligne_type']=='[A]'] != avantages_total[variable][avantages_total['ligne_type']=='[A]']).sum())


n_groups = len(var) # data to plot

fig, ax = plt.subplots(figsize=(15, 6)) # create plot


index = np.arange(n_groups)
bar_width = 0.35
opacity = 1

rects1 = plt.bar(index, modif_par_var_1, bar_width,
                 alpha=opacity,
                 color='b',
                 label='Séries brutes')


rects2 = plt.bar(index + bar_width, modif_par_var_2 , bar_width,
                 alpha=opacity,
                 color='y',
                 label='Séries avec données INSEE')

plt.ylim(0, 30000) #ax.axhline(y = modalites_modifiees[0]) #ax.axhline(y = taille_données_transparence[0])


plt.xlabel('Variable anonymisée')
plt.ylabel('Nombre de valeurs modifiées')
plt.title('Modification de valeurs')
plt.xticks(index + bar_width, var)
plt.legend()

plt.tight_layout()
plt.show()
