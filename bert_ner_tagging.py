# -*- coding: utf-8 -*-
"""BERT_NER_Tagging.ipynb

Automatically generated by Colaboratory.

Original file is located at
    https://colab.research.google.com/drive/18v64TadNcUhfURPWke3cli-NVVNh-kVy

## Importing all the libraries
"""

!pip install pytorch_pretrained_bert
!pip install bert

import os
import sys
import torch
import nltk
import pdb
import pickle
import numpy as np
import pandas as pd
import torch.nn as nn
from torch.utils import data
import torch.optim as optim
from pytorch_pretrained_bert import BertTokenizer
from pytorch_pretrained_bert import BertModel
from sklearn.metrics import f1_score
from sklearn.metrics import accuracy_score
from tqdm import tqdm_notebook as tqdm

from google.colab import drive
drive.mount('/content/drive')

"""
Checking if the machine has the "GPU" unit for the computation otherwise selecting the "CPU"
"""

def get_device():
	device = 'cuda' if torch.cuda.is_available() else 'cpu'
	return device

"""
Getting BERT Tokenizer from the "bert-based-cased" mode. 
This model is pretrained on thousands of Books and Wikipedia Articles.
"""
def get_tokenizer():
	tokenizer = BertTokenizer.from_pretrained('bert-base-cased', do_lower_case=False)
	return tokenizer

class PosDataset(data.Dataset):
    def __init__(self, tagged_sents,tokenizer,tag2idx,idx2tag):
        sents, tags_li = [], [] # list of lists
        self.tokenizer = tokenizer
        self.tag2idx = tag2idx
        self.idx2tag = idx2tag
        for sent in tagged_sents:
            words = [word_pos[0] for word_pos in sent]
            tags = [word_pos[1] for word_pos in sent]
            sents.append(["[CLS]"] + words + ["[SEP]"])
            tags_li.append(["<pad>"] + tags + ["<pad>"])
        self.sents, self.tags_li = sents, tags_li

    def __len__(self):
        return len(self.sents)

    def __getitem__(self, idx):
        words, tags = self.sents[idx], self.tags_li[idx] # words, tags: string list

        # We give credits only to the first piece.
        x, y = [], [] # list of ids
        is_heads = [] # list. 1: the token is the first piece of a word
        for w, t in zip(words, tags):
            tokens = self.tokenizer.tokenize(w) if w not in ("[CLS]", "[SEP]") else [w]
            xx = self.tokenizer.convert_tokens_to_ids(tokens)

            is_head = [1] + [0]*(len(tokens) - 1)

            t = [t] + ["<pad>"] * (len(tokens) - 1)  # <PAD>: no decision
            yy = [self.tag2idx[each] for each in t]  # (T,)

            x.extend(xx)
            is_heads.extend(is_head)
            y.extend(yy)

        assert len(x)==len(y)==len(is_heads), "len(x)={}, len(y)={}, len(is_heads)={}".format(len(x), len(y), len(is_heads))

        # seqlen
        seqlen = len(y)

        # to string
        words = " ".join(words)
        tags = " ".join(tags)
        return words, x, is_heads, tags, y, seqlen

"""
This function is responsible for providing propoer padding to the sentences according to the batch size.
"""
def pad(batch):
    '''Pads to the longest sample'''
    f = lambda x: [sample[x] for sample in batch]
    words = f(0)
    is_heads = f(2)
    tags = f(3)
    seqlens = f(-1)
    maxlen = np.array(seqlens).max()

    f = lambda x, seqlen: [sample[x] + [0] * (seqlen - len(sample[x])) for sample in batch] # 0: <pad>
    x = f(1, maxlen)
    y = f(-2, maxlen)
    f = torch.LongTensor
    return words, f(x), is_heads, tags, f(y), seqlens
"""
BERT Layer Architecture
This class is Deep Neural Network class in which we are using BERT implementation and 
adding a Linear layer which is converting the BERT 768 vector output to the size of the tags.
"""
class Net(nn.Module):
    def __init__(self, vocab_size=None,device = None):
        super().__init__()
        self.bert = BertModel.from_pretrained('bert-base-cased')

        self.fc = nn.Linear(768, vocab_size)
        self.device = device

    def forward(self, x, y):
        x = x.to(self.device)
        y = y.to(self.device)
        
        if self.training:
            self.bert.train()
            encoded_layers, _ = self.bert(x)
            enc = encoded_layers[-1]
        else:
            self.bert.eval()
            with torch.no_grad():
                encoded_layers, _ = self.bert(x)
                enc = encoded_layers[-1]
        
        logits = self.fc(enc)
        y_hat = logits.argmax(-1)
        return logits, y, y_hat
"""
This function is responsible for the training the extra 1 layer on the top of the pretrained BERT model
to fine-tune the BERT model on our dataset.
For each epoch, we are using batching to optimize the trainign speed.
"""
def train(model, iterator, optimizer, criterion):
    model.train()
    for j in range(20):
      for i, batch in enumerate(iterator):
          words, x, is_heads, tags, y, seqlens = batch
          _y = y # for monitoring
          optimizer.zero_grad()
          logits, y, _ = model(x, y) # logits: (N, T, VOCAB), y: (N, T)

          logits = logits.view(-1, logits.shape[-1]) # (N*T, VOCAB)
          y = y.view(-1)  # (N*T,)

          loss = criterion(logits, y)
          loss.backward()

          optimizer.step()

          if i%10==0: # monitoring
              print("step: {}, loss: {}".format(i, loss.item()))
"""
This function is responsible for evaluating the test results and saving the 
predictions in results file which can be further used for calculating the 
precision, recall and F1-Score.
At the end, this function also calculated the accuracy on the test dataset from 
the true and predicted labels.
"""
def eval(model, iterator,tag2idx,idx2tag):
    model.eval()

    Words, Is_heads, Tags, Y, Y_hat = [], [], [], [], []
    with torch.no_grad():
        for i, batch in enumerate(iterator):
            words, x, is_heads, tags, y, seqlens = batch

            _, _, y_hat = model(x, y)  # y_hat: (N, T)

            Words.extend(words)
            Is_heads.extend(is_heads)
            Tags.extend(tags)
            Y.extend(y.numpy().tolist())
            Y_hat.extend(y_hat.cpu().numpy().tolist())

    ## gets results and save
    with open("result", 'w') as fout:
        for words, is_heads, tags, y_hat in zip(Words, Is_heads, Tags, Y_hat):
            y_hat = [hat for head, hat in zip(is_heads, y_hat) if head == 1]
            preds = [idx2tag[hat] for hat in y_hat]
            assert len(preds)==len(words.split())==len(tags.split())
            for w, t, p in zip(words.split()[1:-1], tags.split()[1:-1], preds[1:-1]):
                fout.write("{} {} {}\n".format(w, t, p))
            fout.write("\n")
            
    ## calc metric
    y_true =  np.array([tag2idx[line.split()[1]] for line in open('result', 'r').read().splitlines() if len(line) > 0])
    y_pred =  np.array([tag2idx[line.split()[2]] for line in open('result', 'r').read().splitlines() if len(line) > 0])

    acc = (y_true==y_pred).astype(np.int32).sum() / len(y_true)

    print("acc=%.2f"%acc)
"""
This function is responsible for getting the predictions on the test dataset. 
For each of the test dataset Evaluation is called to get the predictions from the model.
"""
def test(model, iterator,tag2idx,idx2tag):
	model.eval()
	Words, Is_heads, Tags, Y, Y_hat = [], [], [], [], []
	with torch.no_grad():
		for i, batch in enumerate(iterator):
			words, x, is_heads, tags, y, seqlens = batch

		_, _, y_hat = model(torch.tensor(x), torch.tensor(y))  # y_hat: (N, T)

		Words.extend(words)
		Is_heads.extend(is_heads)
		Tags.extend(tags)
		Y.extend(y.numpy().tolist())
		Y_hat.extend(y_hat.cpu().numpy().tolist())

	## get results
	for words, is_heads, tags, y_hat in zip(Words, Is_heads, Tags, Y_hat):
		y_hat = [hat for head, hat in zip(is_heads, y_hat) if head == 1]
		preds = [idx2tag[hat] for hat in y_hat]
		assert len(preds)==len(words.split())==len(tags.split())
		ret_arr = []
		for w, t, p in zip(words.split()[1:-1], tags.split()[1:-1], preds[1:-1]):
			#print("{} {}".format(w, p))
			ret_arr.append(tuple((w,p)))
	return ret_arr
		
def construct_input(sent):
    words = [word_pos for word_pos in sent.split()]
    tags = ['-NONE-' for word_pos in sent.split()]
    #print(tags)
    ret_arr = []
    for i,j in zip(words,tags):
      ret_arr.append(tuple((i,j)))
    return [ret_arr]

!pip install datasets
from datasets import load_dataset
dataset = load_dataset("conll2003")

"""
This function is responsible for creating the tupes of word and its corresponding NER tag and returns the list of list.
For each sentence, it will return the list of tuples having each word and its corresponding actual NER Tag.
"""
def get_tuples_data(dataframe):
  bert_pos_input = []
  bert_ner_input = []
  for name, each_df in dataframe.groupby(by=["sentence_id"]): 
    pos_records = each_df[["words", "ner_labels"]].to_records(index=False)
    bert_ner_input.append(list(pos_records))
  return bert_pos_input, bert_ner_input

"""## We are loading the `Train`, `Test` and `Dev/Validation` dataset from the Conll2003 Data

## Loading The `Conll2003` Dataset for the Training, Validation and Testing the BERT Implementation.
"""

def split_text_label(filename):
    f = open(filename)
    split_labeled_text = []
    sentence = []
    for line in f:
        if len(line)== 0 or line.startswith('-DOCSTART') or line[0]=="\n":
            if len(sentence) > 0:
                split_labeled_text.append(sentence)
                sentence = []
            continue
        splits = line.split(' ')
        sentence.append([splits[1],splits[-1].rstrip("\n")])
    if len(sentence) > 0:
        split_labeled_text.append(sentence)
        sentence = []
    res = []
    for pos,sen in enumerate(split_labeled_text):
      for word in sen:
        r = [pos,word[0],word[1]]
        res.append(r)
    return pd.DataFrame(res,columns=['sentence_id','words','ner_labels'])

df = split_text_label('/content/drive/MyDrive/conll2003/english/eng.train.bioes.conll')
df_validation = split_text_label('/content/drive/MyDrive/conll2003/english/eng.dev.bioes.conll')
df_test = split_text_label('/content/drive/MyDrive/conll2003/english/eng.test.bioes.conll')

bert_pos_input_train, bert_ner_input_train = get_tuples_data(df)
bert_pos_input_validation, bert_ner_input_validation = get_tuples_data(df_validation)
bert_pos_input_test, bert_ner_input_test = get_tuples_data(df_test)

"""
This function is responsbile for all the training and fine-tuning of the BERT Implementation.
We are creating the object of BERT Model and then creating objects for Optimizer and 
Criterion to fine-tune the pretrained weights.
"""
def train_model(model_dir):

	tagged_sents= bert_ner_input_train
	tags = list(set(word_pos[1] for sent in tagged_sents for word_pos in sent))
	tags = ["<pad>"] + tags
	tags_str = ','.join(tags)
	tag2idx = {tag:idx for idx, tag in enumerate(tags)}
	idx2tag = {idx:tag for idx, tag in enumerate(tags)}
	tag2idx["-NONE-"]=len(tag2idx)
	print("our tags are:",tags)
	print("our tag2idx is:",tag2idx)
	from sklearn.model_selection import train_test_split
	train_data = bert_ner_input_train
	test_data = bert_ner_input_validation

	device = get_device() 
	tokenizer = get_tokenizer()
	print(device)

	model = Net(vocab_size=len(tag2idx),device = device)
	model.to(device)
	model = nn.DataParallel(model)

	train_dataset = PosDataset(train_data,tokenizer,tag2idx,idx2tag)
	eval_dataset = PosDataset(test_data,tokenizer,tag2idx,idx2tag)

	train_iter = data.DataLoader(dataset=train_dataset,
                             batch_size=16,
                             shuffle=True,
                             num_workers=1,
                             collate_fn=pad)
	test_iter = data.DataLoader(dataset=eval_dataset,
                             batch_size=32,
                             shuffle=False,
                             num_workers=1,
                             collate_fn=pad)

	optimizer = optim.Adam(model.parameters(), lr = 0.00001)

	criterion = nn.CrossEntropyLoss(ignore_index=0)
	train(model, train_iter, optimizer, criterion)
	eval(model, test_iter,tag2idx,idx2tag)

	print("Saving model...")
	torch.save(model, model_dir + "/pytorch_model.bin")
	print("Model saved")
	tags_arr = [tag2idx,idx2tag]
	print("Pickling tags...")
	fp = open(model_dir +"/tags.pkl","wb")
	pickle.dump(tags_arr,fp)
	fp.close()
	print("Pickling complete...")
	#print(open('result', 'r').read().splitlines()[:100])

if __name__== "__main__":
	if (len(sys.argv) < 2):
		print("Specify model dir to save")
	else:
		try:
			os.mkdir(sys.argv[1])
		except:
			print("Directory already exists")
		train_model(sys.argv[1])

def get_test_sentenses(dataframe):
  test_sentences = []
  i=0
  while i <len(dataframe):
    curr_id = dataframe.iloc[i]['sentence_id']
    j = i
    curr_sentence = []
    while j < len(dataframe) and curr_id == dataframe.iloc[j]['sentence_id']:
      curr_sentence.append(dataframe.iloc[j]['words'])
      j+=1
    test_sentences.append(' '.join(curr_sentence))
    i = j
  return test_sentences, list(dataframe['ner_labels'])

def calculate_accracy(predicted_tags,actual_tag):
  tags=[]
  for sublist in predicted_tags:
    for item in sublist:
      tags.append(item[1])
  acc = accuracy_score(actual_tag, tags)  
  print(acc)
  print('macro',f1_score(actual_tag, tags, average='macro'))
  print('micro',f1_score(actual_tag, tags, average='micro'))
  print('weighted',f1_score(actual_tag, tags, average='weighted'))

def test_model(test_data,actual_test_data):
    model_dir = sys.argv[1]
    predicted_tags = []
    device = get_device() 
    tokenizer = get_tokenizer()
    
    print("Loading model ...")
    model= torch.load("/content/-f/pytorch_model.bin")
    print("Loading model complete")
    print("Loading Pickling tags...")
    fp = open("/content/-f/tags.pkl","rb")
    tags_arr = pickle.load(fp)
    print("Loading Pickling tags complete")
    fp.close()
    
    for text in test_data:
      rt_test_dataset = PosDataset(construct_input(text),tokenizer,tags_arr[0],tags_arr[1])
      rt_test_iter = data.DataLoader(dataset=rt_test_dataset,
                              batch_size=32,
                              shuffle=False,
                              num_workers=1,
                              collate_fn=pad)

      ret_arr = test(model, rt_test_iter,tags_arr[0],tags_arr[1])
      predicted_tags.append(ret_arr)
    return predicted_tags,actual_test_data

"""### Calculating the Accuracy on the Test Dataset using the SkLearn Library"""

test_sentances,test_sentances_tag = get_test_sentenses(df_test)
pt,at = test_model(test_sentances,test_sentances_tag)

def create_out_file(data_set,predicted_tags,actual_tag,file_name):
  p_tags=[]
  flat_list = []
  for s in predicted_tags:
    for sublist in s:
      flat_list.append(sublist)
  for res in flat_list:
    p_tags.append(res)
  data_set_new = np.array(data_set)
  file_object = open(file_name+'.out', 'a')
  for pos,each in enumerate(data_set_new):
    s = str(each[0])+' '+each[1]+' '+each[2]+' '+(p_tags[pos][1])+'\n'
    file_object.write(s)

create_out_file(df_test,pt,test_sentances_tag,'test_out')

!perl /content/conlleval.v2 < /content/test_out.out

"""## Evaluating the Test Results using the Perl Script to calculate the Accuracy, Precision, Recall and F-1 Score."""

dev_sentances,dev_sentances_tag = get_test_sentenses(df_validation)
p,a = test_model(dev_sentances,dev_sentances_tag)

create_out_file(df_validation,p,a,'dev_out')

!perl /content/conlleval.v2 < /content/dev_out.out