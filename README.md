# RepML
This repository contains all the code written for the experiments of my MSc thesis in computer science at the University of Padova (Italy): **A deep learning approach for discursive repertoires prediction in online texts.**

## General info
The project proposes a NLP pipeline for the prediction of discurive repertoires. More information in the thesis pdf.
The pipeline is then used to create sentence representation and used to solve the [SENTIPOLC challenge](http://www.di.unito.it/~tutreeb/sentipolc-evalita16/) obtaining the state of the art in Irony detection task:

|                 | F1 Iro | F1 Non-iro | F1 Macro |
|-----------------|--------|------------|----------|
| **DR-SVM**      | 0.42   | 0.93       | 0.67     |
| LSTM            | -      | -          | 0.62     |
| AlBERTo         | 0.28   | 0.94       | 0.61     |
| CNN             | -      | -          | 0.54     |
| tweet2check16.c | 0.17   | 0.91       | 0.54     |


All the experiments discussed in the thesis are implementend in this repository.

## Structure
* **data**: datasets grouped by raw, processed ...
* **notebooks**: notebooks for data analysis or quick prototyping. 
* **src**: Structured code for models training and testing.
* **config**: YAML files for scripts configuration

## Experiments
Each script in src/scripts allows to replicate the experiments.

WARNING: Remember to set Neptune logger token or comment logger lines in the script if you don't want to log results. Remember to set the huggingface token if you want to save the trained model (save=True in the config files)
To replicate results leave default seed in config files.

Scripts:
* bert_cls_train.py (Chapter 3): train and test of BERT for discursive repertories classification.
* bert_cls_seg.py (Chapter 4): train and test of BERT for text segmentation as a supervised task.
* pipeline.py (Chapter 5): test of the entire pipeline for dicursive repertoires prediciton (from text to a sequnence of DR).
* svm_train.py (Chapter 6): script for SENTIPOLC challenge. Extraction of sentence embedding based on DR and then we train an SVM that takes in input BERT embeddings for solving the challange. 
