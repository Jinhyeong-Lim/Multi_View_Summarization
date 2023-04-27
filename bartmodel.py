from typing import List, Optional, Tuple, Union
import torch
from torch import nn
from torch.nn import CrossEntropyLoss

from sklearn.cluster import KMeans, DBSCAN
from sklearn.decomposition import PCA

import numpy as np
from numpy import dot
from numpy.linalg import norm

import random
import pandas as pd
import matplotlib.pyplot as plt

from dataclasses import dataclass
from transformers.utils import (
    ModelOutput,
    logging
)
from transformers.utils import (
    add_end_docstrings,
    replace_return_docstrings,
)

import datasets

from transformers import AutoTokenizer

from transformers.modeling_utils import PreTrainedModel
from transformers.models.bart.modeling_bart import (
    BartPretrainedModel,
    BaseModelOutput,
    Seq2SeqModelOutput,
    Seq2SeqLMOutput,
    BartConfig,
    BartEncoder,
    BartDecoder,
    BART_INPUTS_DOCSTRING,
    _CHECKPOINT_FOR_DOC,
    _CONFIG_FOR_DOC,
    _EXPECTED_OUTPUT_SHAPE,
    BART_GENERATION_EXAMPLE,
    shift_tokens_right,
    add_code_sample_docstrings,
    add_start_docstrings_to_model_forward,
)

import os
os.environ["CUDA_DEVICE_ORDER"] = "PCI_BUS_ID"
os.environ["CUDA_VISIBLE_DEVICES"] = "1"
device = torch.device("cuda")
print(f"device : {device}")
logger = logging.get_logger(__name__)

model_name = "facebook/bart-large"

# 고정할 시드 값 설정
seed = 100
random.seed(seed)

# PyTorch 시드 고정
torch.manual_seed(seed)

# NumPy 시드 고정
np.random.seed(seed)


@dataclass
class CustomSeq2SeqLMOutput(Seq2SeqLMOutput):
    loss: Optional[torch.FloatTensor] = None
    logits: torch.FloatTensor = None
    past_key_values: Optional[Tuple[Tuple[torch.FloatTensor]]] = None
    decoder_hidden_states: Optional[Tuple[torch.FloatTensor]] = None
    decoder_attentions: Optional[Tuple[torch.FloatTensor]] = None
    cross_attentions: Optional[Tuple[torch.FloatTensor]] = None
    encoder_last_hidden_state: Optional[torch.FloatTensor] = None
    encoder_hidden_states: Optional[Tuple[torch.FloatTensor]] = None
    encoder_attentions: Optional[Tuple[torch.FloatTensor]] = None
    ctr_loss: torch.FloatTensor = None

@dataclass
class CustomSeq2SeqModelOutput(Seq2SeqModelOutput):
    last_hidden_state: torch.FloatTensor = None
    past_key_values: Optional[Tuple[Tuple[torch.FloatTensor]]] = None
    decoder_hidden_states: Optional[Tuple[torch.FloatTensor]] = None
    decoder_attentions: Optional[Tuple[torch.FloatTensor]] = None
    cross_attentions: Optional[Tuple[torch.FloatTensor]] = None
    encoder_last_hidden_state: Optional[torch.FloatTensor] = None
    encoder_hidden_states: Optional[Tuple[torch.FloatTensor]] = None
    encoder_attentions: Optional[Tuple[torch.FloatTensor]] = None
    ctr_speaker_loss: torch.FloatTensor = None
    ctr_topic_loss: torch.FloatTensor = None

class BartModel(BartPretrainedModel):
    _keys_to_ignore_on_load_missing = ["encoder.embed_tokens.weight", "decoder.embed_tokens.weight"]

    def __init__(self, config: BartConfig):
        super().__init__(config)
        
        padding_idx, vocab_size = config.pad_token_id, config.vocab_size
        self.shared = nn.Embedding(vocab_size, config.d_model, padding_idx)

        self.encoder = BartEncoder(config, self.shared)
        self.decoder = BartDecoder(config, self.shared)
        
        self.num_try = 0

        # Initialize weights and apply final processing
        self.post_init()

    def get_input_embeddings(self):
        return self.shared

    def set_input_embeddings(self, value):
        self.shared = value
        self.encoder.embed_tokens = self.shared
        self.decoder.embed_tokens = self.shared

    def get_encoder(self):
        return self.encoder

    def get_decoder(self):
        return self.decoder

    def speaker_aware(self, enc_speaker, ctr_margin, speaker_input_ids, bench_speaker):
        # print(f"speaker!!")
        # print(f"============================================")
        # print(f"turn_num = enc_speaker.shape : {enc_speaker.shape[0]}")
        # print(f"enc_speaker : {enc_speaker}")

        enc_negative, enc_positive = [], []

        num_turn = enc_speaker.shape[0]
        cos = nn.CosineSimilarity(dim=0, eps=1e-8)
        # sim = torch.dist(enc_speaker[i], enc_speaker[bench_speaker], p=2.0)
        num_speakers = len(speaker_input_ids)
        num_speaker_unique = len(list(set([int(i[0]) for i in speaker_input_ids])))

        # turns = range(1, num_turn)
        # for i in turns:
        #     if torch.eq(speaker_input_ids[i][0], speaker_input_ids[bench_speaker][0]):
        #         # print("same")
        #         enc_positive.append(enc_speaker[i])
        #     else:
        #         # print("diff")
        #         enc_negative.append(enc_speaker[i])

        # if len(enc_positive) > 0 and len(enc_negative) > 0:
        #     positive_sample = random.choice(enc_positive)
        #     negative_sample = random.choice(enc_negative)
        #     positive_l2 = torch.dist(positive_sample, enc_speaker[bench_speaker], p=2.0)
        #     negative_l2 = torch.dist(negative_sample, enc_speaker[bench_speaker], p=2.0)
        # else:
        #     ctr_speaker_loss = torch.zeros(1, device=device)
        #     return ctr_speaker_loss
        
        # softmax_sim = torch.stack([1-positive_l2, 1-negative_l2])
        # softmax_sim_out = nn.functional.softmax(softmax_sim, dim=0)

        # relu = nn.ReLU()
        # positive_softmax = softmax_sim_out[0]
        # negative_softmax = softmax_sim_out[1]

        # ctr_speaker_loss = relu(ctr_margin - (positive_softmax - negative_softmax))

        ctr_speaker_loss_means = []
        for speaker in range(1, num_speaker_unique):
            bench_speaker = speaker
            turns = range(1, num_turn)
            # print(f"turns : {turns}")
            for i in turns:
                # print(f"{torch.eq(speaker_input_ids[i][0], speaker_input_ids[bench_speaker][0])}=============================")
                # print(f"speaker : {speaker_input_ids[i]}")
                if torch.eq(speaker_input_ids[i][0], speaker_input_ids[bench_speaker][0]):
                    # print("same")
                    enc_positive.append(enc_speaker[i])
                else:
                    # print("diff")
                    enc_negative.append(enc_speaker[i])

            # print(f"positive_sim_idx : {positive_sim_idx}")
            # print(f"negative_sim_idx : {negative_sim_idx}")

            if len(enc_positive) > 0 and len(enc_negative) > 0:
                # print(f"enc_positive : {enc_positive}")
                # print(f"enc_negative : {enc_negative}")

                relu = nn.ReLU()

                positive_sample_l2 = torch.stack([torch.dist(positive, enc_speaker[bench_speaker], p=2.0) for positive in enc_positive])
                # print(f"positive_sample_l2 : {positive_sample_l2}")
                negative_sample_l2 = torch.stack([torch.dist(negative, enc_speaker[bench_speaker], p=2.0) for negative in enc_negative])
                # print(f"positive_sample_l2 : {negative_sample_l2}")

                ctr_speaker_loss_lists = []
                for negative_sample in negative_sample_l2:
                    for positive_sample in positive_sample_l2:
                        softmax_sim_out = nn.functional.softmax(torch.stack([1-positive_sample, 1-negative_sample]), dim=0)
                        positive_softmax = softmax_sim_out[0]
                        negative_softmax = softmax_sim_out[1]
                        ctr_speaker_loss_lists.append(relu(ctr_margin - (positive_softmax - negative_softmax)))
                ctr_speaker_loss_list = torch.stack(ctr_speaker_loss_lists)
                # print(f"ctr_speaker_loss_list : {ctr_speaker_loss_list}")
                ctr_speaker_loss = torch.mean(ctr_speaker_loss_list)
                # print(f"ctr_speaker_loss : {ctr_speaker_loss.grad_fn}")
                ctr_speaker_loss_means.append(ctr_speaker_loss)
            else:
                # print(f"1, {device}")
                ctr_speaker_loss = torch.zeros(1, device=device)
                # print(f"ctr_speaker_loss : {ctr_speaker_loss}")
                return ctr_speaker_loss

        if len(ctr_speaker_loss_means) == 0:
            ctr_speaker_loss = torch.zeros(1, device=device)
            # print(f"ctr_speaker_loss : {ctr_speaker_loss}")
            return ctr_speaker_loss
        else:
            ctr_speaker_loss_result = torch.stack(ctr_speaker_loss_means)
            # print(f"------------ctr_speaker_loss_means : {torch.stack(ctr_speaker_loss_means)}--------------")
            # print(f"============ctr_speaker_loss_result : {ctr_speaker_loss_result}==============")
            return ctr_speaker_loss_result

            # print(f"=positive_sim={type(positive_sim)}")
            # print(f"=negative_sim={type(negative_sim)}")
            # softmax_sim = torch.Tensor([positive_l2, negative_l2])

            # softmax_sim = torch.stack([1-positive_l2, 1-negative_l2])
            # softmax_sim = torch.stack([positive_sim, negative_sim])
            # softmax_sim = torch.stack([positive_sim - positive_l2, negative_sim - negative_l2])
            # print(f"softmax_sim : {softmax_sim}")
            # softmax_sim_out = nn.functional.softmax(softmax_sim, dim=0)
            # print(f"softmax_sim_out : {softmax_sim_out}")

            # relu = nn.ReLU()
            # positive_softmax = softmax_sim_out[0]
            # negative_softmax = softmax_sim_out[1]
            # print(f"positive_softmax : {positive_softmax}")
            # print(f"negative_softmax : {negative_softmax}")
            # print(f"ctr_margin - (positive_softmax - negative_softmax) : {ctr_margin - (positive_softmax - negative_softmax)}")

            # ctr_speaker_loss = relu(ctr_margin - (positive_softmax - negative_softmax))
            # print(f"ctr_speaker_loss : {ctr_speaker_loss}")

            
            # # 고정할 시드 값 설정
            # seed = 42
            # random.seed(seed)

            # # PyTorch 시드 고정
            # torch.manual_seed(seed)

            # # NumPy 시드 고정
            # np.random.seed(seed)

        # return ctr_speaker_loss
    
    def topic_aware(self, enc_utterance, ctr_margin, cluster_mode, raw_data):
        df = pd.DataFrame()
        # for i in range(enc_utterance.shape[0]):

        # for rep in enc_utterance:
        #     print(f"rep : {rep.shape}")
        
        # enc_utterance = torch.stack([enc_utterance[0][i][:j] for i, j in zip(range(enc_utterance.shape[1]), no_padding_len)])
        # enc_utterance = [enc_utterance[0][i][:j] for i, j in zip(range(enc_utterance.shape[1]), no_padding_len)]
        # print(f"enc_utterance aa : {len(enc_utterance)}")
        num_turn = len(enc_utterance)
        # raw_data.split("<sep>")
        enc_rep = [rep.cpu().detach().numpy() for rep in enc_utterance]
        # print(f"enc_rep : {enc_rep}")

        if num_turn < 3:
            return torch.zeros(1, device=device)

        if cluster_mode == 0:
            # sse = []
            # for i in range(1, 11):
            #     km = KMeans(n_clusters=i, init='k-means++', random_state=0)
            #     km.fit(enc_utterance.cpu().detach().numpy())
            #     sse.append(km.inertia_)

            # plt.plot(range(1, 11), sse, marker='o')
            # plt.xlabel('n_clusters')
            # plt.xlabel('SSE')
            # plt.show()
            # plt.savefig('kmeans_n_clusters.png')
            # plt.clf()


            num_cluster = 2
            kmeans = KMeans(n_clusters=num_cluster, init='k-means++').fit(enc_utterance.cpu().detach().numpy())
            # print('[K-평균 군집 분석 결과]')
            # print('###########################################')
            # print(kmeans.labels_)
            df = pd.DataFrame({'enc_rep' : enc_rep, 'cluster' : kmeans.labels_})
            # df['cluster'] = kmeans.labels_
            # print(f"{df.head()}")

            # centroid : K-Means가 구한 각 Cluster들의 Topic
            centroid = torch.Tensor(kmeans.cluster_centers_).to(device)
            # print(f"kmeans.cluster_centers_ : {centroid}")

            bench_cluster = df["cluster"][0]
            bench_turn = enc_utterance[0]
            # print(f"bench_cluster : {bench_cluster}")
            # print(f"bench_turn : {bench_turn.shape}")

            # positive_idx = df[df["cluster"] == bench_cluster][1:].index.to_numpy()
            # negative_idx = df[df["cluster"] != bench_cluster].index.to_numpy()
            
            # if len(positive_idx) < 1 or len(negative_idx) < 1:
            #     return torch.zeros(1, device=device)

            # positive = enc_utterance[positive_idx]
            # negative = enc_utterance[negative_idx]
            # print(f"positive : {positive.shape}")
            # print(f"negative : {negative.shape}")

            # print(f"bench_cluster : {1 if bench_cluster == 1 else 0}")
            # print(f"^bench_cluster : {0 if bench_cluster == 1 else 1}")

            # negative_sample = min([torch.dist(n, centroid[1 if bench_cluster == 1 else 0], p=2.0) for n in negative])
            # positive_sample = min([torch.dist(p, centroid[0 if bench_cluster == 1 else 1], p=2.0) for p in positive])
            # negative_sample = max([cos(n, centroid[1 if bench_cluster == 1 else 0]) for n in negative])
            # positive_sample = max([cos(p, centroid[0 if bench_cluster == 1 else 1]) for p in positive])

            # #############
            # negative_sample_l2 = max([torch.dist(n, centroid[1 if bench_cluster == 1 else 0], p=2.0) for n in negative])
            # positive_sample_l2 = max([torch.dist(p, centroid[0 if bench_cluster == 1 else 1], p=2.0) for p in positive])

            # cos = nn.CosineSimilarity(dim=0, eps=1e-8)
            # negative_sample_sim = max([cos(n, centroid[1 if bench_cluster == 1 else 0]) for n in negative])
            # positive_sample_sim = max([cos(p, centroid[0 if bench_cluster == 1 else 1]) for p in positive])

            # softmax_sim = torch.stack([positive_sample_sim - positive_sample_l2, negative_sample_sim - negative_sample_l2])

            # softmax_sim_out = nn.functional.softmax(softmax_sim, dim=0)

            # relu = nn.ReLU()
            # positive_softmax = softmax_sim_out[0]
            # negative_softmax = softmax_sim_out[1]
            # # print(f"positive_softmax : {positive_softmax}")
            # # print(f"negative_softmax : {negative_softmax}")
            
            # ctr_topic_loss = relu(ctr_margin - (positive_softmax - negative_softmax))
            # #################

            relu = nn.ReLU()
            ctr_topic_loss_means = []
            for bench in range(num_cluster):
                positive_idx = df[df["cluster"] == bench][1:].index.to_numpy()
                negative_idx = df[df["cluster"] != bench].index.to_numpy()
                
                if len(positive_idx) < 1 or len(negative_idx) < 1:
                    return torch.zeros(1, device=device)

                positive = enc_utterance[positive_idx]
                negative = enc_utterance[negative_idx]

                negative_sample_l2 = [torch.dist(n, centroid[bench], p=2.0) for n in negative]
                positive_sample_l2 = [torch.dist(p, centroid[bench], p=2.0) for p in positive]
                
                ctr_topic_loss_lists = []
                for negative_sample in negative_sample_l2:
                    for positive_sample in positive_sample_l2:
                        softmax_sim_out = nn.functional.softmax(torch.stack([1-positive_sample, 1-negative_sample]), dim=0)
                        positive_softmax = softmax_sim_out[0]
                        negative_softmax = softmax_sim_out[1]
                        ctr_topic_loss_lists.append(relu(ctr_margin - (positive_softmax - negative_softmax)))
                ctr_topic_loss_list = torch.stack(ctr_topic_loss_lists)
                ctr_topic_loss = torch.mean(ctr_topic_loss_list)
                ctr_topic_loss_means.append(ctr_topic_loss)
            
            ctr_topic_loss_result = torch.stack(ctr_topic_loss_means)
            # print(f"------------ctr_speaker_loss_means : {torch.stack(ctr_topic_loss_means)}--------------")
            print(f"============ctr_topic_loss_result : {ctr_topic_loss_result}==============")
            return ctr_topic_loss_result

            # print(f"before positive_l2 : {positive_l2}")
            # print(f"before negative_l2 : {negative_l2}")


            # negative_l2 = torch.Tensor([torch.dist(n, centroid[1 if bench_cluster == 1 else 0], p=2.0) for n in negative])
            # positive_l2 = torch.Tensor([torch.dist(p, centroid[0 if bench_cluster == 1 else 1], p=2.0) for p in positive])
            
            # print(f"after positive_l2 : {positive_l2}")
            # print(f"after negative_l2 : {negative_l2}")

            # positive_sample = random.choice(positive_l2)
            # negative_sample = random.choice(negative_l2)
            # positive_sample = torch.min(positive_l2)
            # negative_sample = torch.min(negative_l2)

            # print(f"positive_sample : {positive_sample}")
            # print(f"negative_sample : {negative_sample}")

            # softmax_sim = torch.stack([positive_sample, negative_sample])
            # softmax_sim = torch.Tensor([positive_sim - positive_l2, negative_sim - negative_l2])
            # print(f"softmax_sim : {softmax_sim}")
            

            # relu = nn.ReLU()
            # positive_softmax = softmax_sim_out[0]
            # negative_softmax = softmax_sim_out[1]
            # # print(f"positive_softmax : {positive_softmax}")
            # # print(f"negative_softmax : {negative_softmax}")
            
            # ctr_topic_loss = relu(ctr_margin - (positive_softmax - negative_softmax))
            # print(f"ctr_topic_loss : {ctr_topic_loss}")
            # return ctr_topic_loss

            # print(f'PCA로 차원 축소 후 KMeans 결과 시각화')
            # pca = PCA(n_components = 2)
            # pca_transformed = pca.fit_transform(enc_utterance.detach().numpy())
            # print(f"pca_transformed : {len(pca_transformed)}")

            # print(f"enc_utterance : {enc_utterance.shape}")
            # df['raw_data'] = raw_data
            # df['cluster'] = kmeans.labels_
            # df['pca_x'] = pca_transformed[:, 0]  #x좌표
            # df['pca_y'] = pca_transformed[:, 1]  #y좌표
            # # print(df)
            # pca_centroid = pca.fit_transform(kmeans.cluster_centers_)
            # # centroid : K-Means가 구한 각 Cluster들의 Topic
            # centroid = kmeans.cluster_centers_
            # print(f"kmeans.cluster_centers_ : {centroid}")

            # # 클러스터별 인덱스 추출
            # marker = []
            # for i in range(num_cluster):
            #     marker.append(df[df['cluster'] == i].index)

            #scatter plot
            # for i, markers in zip(range(num_cluster), ['o', 's', '^', "v", "D"]):
            #     plt.scatter(x = df.loc[marker[i], 'pca_x'], y = df.loc[marker[i], 'pca_y'], marker = markers)

            # for i in range(num_cluster):
            #     plt.scatter(x = pca_centroid[i][0], y = pca_centroid[i][1], marker="*")
            
            # plt.xlabel('PCA1')
            # plt.ylabel('PCA2')
            # plt.title(f'{num_cluster} Kmeans Clusters Visualization by 2 PCA Components')
            # plt.legend(['cluster'+str(i) for i in range(num_cluster)])
            # for i, x, y in zip(range(len(pca_transformed)), df['pca_x'], df['pca_y']):
            #     plt.annotate(i, (x, y), textcoords="offset points", xytext=(0, 10), ha="center")

            # plt.show()
            # plt.savefig('kmeans_result'+str(self.num_try)+'.png')
            # plt.clf()
            # self.num_try += 1
        elif cluster_mode == 1:
            turn_topics = [0 if i < num_turn//2 else 1 for i in range(num_turn)]
            centroid = torch.stack([enc_utterance[num_turn//4], enc_utterance[num_turn//2 + num_turn//4]])
            df = pd.DataFrame({'enc_rep' : enc_rep, 'cluster' : turn_topics})

            relu = nn.ReLU()
            ctr_topic_loss_means = []
            for bench in range(num_turn):
                positive_idx = df[df["cluster"] == bench][1:].index.to_numpy()
                negative_idx = df[df["cluster"] != bench].index.to_numpy()
                if len(positive_idx) >= 1 and len(negative_idx) >= 1:
                    positive = enc_utterance[positive_idx]
                    negative = enc_utterance[negative_idx]

                    negative_sample_l2 = [torch.dist(n, centroid[bench], p=2.0) for n in negative]
                    positive_sample_l2 = [torch.dist(p, centroid[bench], p=2.0) for p in positive]
                    
                    ctr_topic_loss_lists = []
                    for negative_sample in negative_sample_l2:
                        for positive_sample in positive_sample_l2:
                            softmax_sim_out = nn.functional.softmax(torch.stack([1-positive_sample, 1-negative_sample]), dim=0)
                            positive_softmax = softmax_sim_out[0]
                            negative_softmax = softmax_sim_out[1]
                            ctr_topic_loss_lists.append(relu(ctr_margin - (positive_softmax - negative_softmax)))
                    ctr_topic_loss_list = torch.stack(ctr_topic_loss_lists)
                    ctr_topic_loss = torch.mean(ctr_topic_loss_list)
                    ctr_topic_loss_means.append(ctr_topic_loss)
            
            # print(f"ctr_topic_loss : {ctr_topic_loss_means}")
            ctr_topic_loss_result = torch.stack(ctr_topic_loss_means)
            # print(f"============ctr_topic_loss_result : {ctr_topic_loss_result}==============")
            return ctr_topic_loss_result


        elif cluster_mode == 2:
            # epsilon, 최소 샘플 개수 설정
            dbscan = DBSCAN(eps=8, min_samples=5).fit(enc_utterance.detach().numpy())
            print('[DBSCAN 군집 분석 결과]')
            print('###########################################')
            print(f"dbscan : {dbscan.labels_}")

            print(f'PCA로 차원 축소 후 DBSCAN 결과 시각화')
            pca = PCA(n_components = 2)
            pca_transformed = pca.fit_transform(enc_utterance.detach().numpy())
            print(f"pca_transformed : {len(pca_transformed)}")

            df = pd.DataFrame()
            df['cluster'] = dbscan.labels_
            df['pca_x'] = pca_transformed[:, 0]  #x좌표
            df['pca_y'] = pca_transformed[:, 1]  #y좌표
            print(df)
            # pca_centroid = pca.fit_transform(dbscan.core_sample_indices_)
            # print(f"dbscan.core_sample_indices_ : {pca_centroid}")

            # 클러스터별 인덱스 추출
            marker = []
            num_cluster = len(set(dbscan.labels_))
            for i in range(num_cluster):
                marker.append(df[df['cluster'] == i].index)

            #scatter plot
            for i, markers in zip(range(num_cluster), ['o', 's', '^', "v", "D"]):
                plt.scatter(x = df.loc[marker[i], 'pca_x'], y = df.loc[marker[i], 'pca_y'], marker = markers)

            # for i in range(len(dbscan.labels_)):
            #     plt.scatter(x = pca_centroid[i][0], y = pca_centroid[i][1], marker="*")
            
            plt.xlabel('PCA1')
            plt.ylabel('PCA2')
            plt.title(f'{num_cluster} DBSCAN Clusters Visualization by 2 PCA Components')
            plt.legend(['cluster'+str(i) for i in range(num_cluster)])
            plt.show()
            plt.savefig('dbscan_result'+str(self.num_try)+'.png')
            plt.clf()
            self.num_try += 1 

        print(f"====================<df>=====================")
        print(f"{df}")
        # softmax_sim_out = nn.functional.softmax(softmax_sim, dim=0)
        # positive_softmax = softmax_sim_out[:positive_sim_idx].max()
        # negative_softmax = softmax_sim_out[positive_sim_idx:positive_sim_idx+negative_sim_idx].max()
        # relu = nn.ReLU()
        # ctr_speaker_loss = relu(ctr_margin - (positive_softmax - negative_softmax))

        # num_topics = 5
        # chunksize = 2000
        # passes = 20
        # iterations = 400
        # eval_every = None

        # temp = dictionary[0]
        # id2word = dictionary.id2token

        # model = LdaModel(
        #     corpus=corpus,
        #     id2word=id2word,
        #     chunksize=chunksize,
        #     alpha='auto',
        #     eta='auto',
        #     iterations=iterations,
        #     num_topics=num_topics,
        #     passes=passes,
        #     eval_every=eval_every
        # )

        return
    
    @add_start_docstrings_to_model_forward(BART_INPUTS_DOCSTRING)
    @add_code_sample_docstrings(
        checkpoint=_CHECKPOINT_FOR_DOC,
        output_type=Seq2SeqModelOutput,
        config_class=_CONFIG_FOR_DOC,
        expected_output=_EXPECTED_OUTPUT_SHAPE,
    )
    def forward(
        self,
        input_ids: torch.LongTensor = None,
        attention_mask: Optional[torch.Tensor] = None,
        decoder_input_ids: Optional[torch.LongTensor] = None,
        decoder_attention_mask: Optional[torch.LongTensor] = None,
        head_mask: Optional[torch.Tensor] = None,
        decoder_head_mask: Optional[torch.Tensor] = None,
        cross_attn_head_mask: Optional[torch.Tensor] = None,
        encoder_outputs: Optional[List[torch.FloatTensor]] = None,
        past_key_values: Optional[List[torch.FloatTensor]] = None,
        inputs_embeds: Optional[torch.FloatTensor] = None,
        decoder_inputs_embeds: Optional[torch.FloatTensor] = None,
        use_cache: Optional[bool] = None,
        output_attentions: Optional[bool] = None,
        output_hidden_states: Optional[bool] = None,
        return_dict: Optional[bool] = None,
        all_special_ids: Optional[List] = None,
        raw_data: Optional[datasets.dataset_dict.DatasetDict] = None,
        ctr_mode: int = 0,
    ) -> Union[Tuple, Seq2SeqModelOutput]:
        # different to other models, Bart automatically creates decoder_input_ids from
        # input_ids if no decoder_input_ids are provided
        if decoder_input_ids is None and decoder_inputs_embeds is None:
            if input_ids is None:
                raise ValueError(
                    "If no `decoder_input_ids` or `decoder_inputs_embeds` are "
                    "passed, `input_ids` cannot be `None`. Please pass either "
                    "`input_ids` or `decoder_input_ids` or `decoder_inputs_embeds`."
                )

            decoder_input_ids = shift_tokens_right(
                input_ids, self.config.pad_token_id, self.config.decoder_start_token_id
            )

        output_attentions = output_attentions if output_attentions is not None else self.config.output_attentions
        output_hidden_states = (
            output_hidden_states if output_hidden_states is not None else self.config.output_hidden_states
        )
        use_cache = use_cache if use_cache is not None else self.config.use_cache
        return_dict = return_dict if return_dict is not None else self.config.use_return_dict

        if encoder_outputs is None:
            encoder_outputs = self.encoder(
                input_ids=input_ids,
                attention_mask=attention_mask,
                head_mask=head_mask,
                inputs_embeds=inputs_embeds,
                output_attentions=output_attentions,
                output_hidden_states=output_hidden_states,
                return_dict=return_dict,
            )
        
        # If the user passed a tuple for encoder_outputs, we wrap it in a BaseModelOutput when return_dict=True
        elif return_dict and not isinstance(encoder_outputs, BaseModelOutput):
            encoder_outputs = BaseModelOutput(
                last_hidden_state=encoder_outputs[0],
                hidden_states=encoder_outputs[1] if len(encoder_outputs) > 1 else None,
                attentions=encoder_outputs[2] if len(encoder_outputs) > 2 else None,
            )
        
        # print("encoder_outputs[0].shape : ", encoder_outputs[0].shape)
        # print(f"input_ids length : {input_ids.shape[1]}")
        # print(f"input_ids : {input_ids[0]}")
        # print(f"all_special_ids : {all_special_ids}")

        tokenizer = AutoTokenizer.from_pretrained(model_name)
        # speaker_tokens = ["P01:", "P02:", "P03:", "P04:", "P05:", "P06:", "P07:", "P08:", "P09:"]
        tokenizer.add_special_tokens({"additional_special_tokens":["<sep>", ":"]})


        if all_special_ids is not None:
            # lang_sep = 4 # 한국어
            lang_sep = 5 # English
            sep_idx = [idx for ids, idx in zip(input_ids[0], range(input_ids.shape[1])) if ids == all_special_ids[lang_sep]]
            speaker_idx = []
            for idx in sep_idx:
                ids = idx
                while ids < len(input_ids[0]) and input_ids[0][ids] != all_special_ids[lang_sep+1]:
                    ids += 1
                speaker_idx.append([idx+1, ids])
            # print(f"speaker_idx : {speaker_idx}")
            # sep_idx.append(input_ids.shape[1])
            # speaker_idx = [element+1 for element in sep_idx[:-1]]
            
            # print(f"sep : {tokenizer.decode(all_special_ids)}")
            utterance_idx = [[start+3, end] for start, end in zip(sep_idx[:-1], sep_idx[1:]) if (start+3) < end]
            speaker_input_ids = [input_ids[0][i[0]:i[1]] for i in speaker_idx]
            # for i in speaker_input_ids:
            #     decoded_ids = tokenizer.decode(i)
            decoded_ids = tokenizer.decode(input_ids[0])
            # print(f"input_ids[0] : {input_ids[0]}")
            # print(f"special_ids : {decoded_ids}")
            # print(f"speaker_input_ids : {speaker_input_ids}")

            # print(f"sep_idx : {sep_idx}")
            # print(f"speaker_idx : {speaker_idx}")
            # print(f"utterance_idx : {utterance_idx}")
            # print(f"all_special_ids : {all_special_ids}")

        if ctr_mode == 0: # 기존 BART만 Training
            ctr_speaker_loss = torch.zeros(1, device=device)
            ctr_topic_loss = torch.zeros(1, device=device)
        elif ctr_mode == 1: # BART + Spaeker-view
            if len(speaker_idx) > 1:
                # print("=======================================")
                # decoded_ids = tokenizer.decode(all_special_ids)
                # print(f"special_ids : {decoded_ids}")
                # print(f"input_ids : {input_ids[0]}")
                # print(f"sep_idx : {sep_idx}")
                # print(f"speaker_idx : {speaker_idx}")
                # print(f"utterance_idx : {utterance_idx}")
                # print(f"all_special_ids : {all_special_ids}")
                # print("=======================================")
                
                # # speaker token들의 Encoder Representation
                # enc_speaker = torch.row_stack([encoder_outputs[0][0][i] for i in speaker_idx])

                # Speaker의 Encoder Representation -> Mean Pooling
                enc_speaker = [encoder_outputs[0][0][i[0]:i[1]] for i in speaker_idx]
                mean_speaker = torch.row_stack([torch.mean(i, 0) for i in enc_speaker])
                # print(f"mean_speaker : {mean_speaker}")
                # print(f"enc_speaker : {enc_speaker.shape}")


                
                # raw = [for i in raw_data]
                
                # print(f"self.num_try : {self.num_try}")
                # decoded_ids = tokenizer.decode(input_ids[0])
                # print(f"raw_data : {decoded_ids}")
                # print(f"enc_speaker : {enc_speaker.shape}")

                ############# 스피커 어웨어 부분 #################
                ctr_speaker_loss = self.speaker_aware(
                                    # enc_speaker=enc_speaker, # speaker의 representation list
                                    enc_speaker=mean_speaker, # speaker의 representation list
                                    ctr_margin=1, # ctrastive learning 시, margin 값
                                    speaker_input_ids=speaker_input_ids, # Dialogue 안 Speaker Token들의 input_ids list
                                    bench_speaker=0 # P01을 기준점 = 0번째 Speaker
                                )
                
                ctr_topic_loss = torch.zeros(1, device=device)
                # print(f"speaker_loss : {ctr_speaker_loss}, ctr_topic_loss : {ctr_topic_loss}")
                # print(f"speaker_loss : {type(ctr_speaker_loss)}, ctr_topic_loss : {type(ctr_topic_loss)}")
                # print(f"speaker_loss : {type(ctr_speaker_loss)}")
                # print(f"speaker_loss : {ctr_speaker_loss}, ctr_topic_loss : {ctr_speaker_loss+ctr_topic_loss}")
                # ctr_speaker_loss = torch.zeros(1, device=device)
            else:
                ctr_speaker_loss = torch.zeros(1, device=device)
                ctr_topic_loss = torch.zeros(1, device=device)
        elif ctr_mode == 2: # koBART + Topic-view
            if len(speaker_idx) > 1:
                # Utterance의 Encoder Representation -> Mean Pooling
                enc_utterance = [encoder_outputs[0][0][i[0]:i[1]] for i in utterance_idx]
                    
                # print("=======================================================================")
                # print(f"sep_idx : {sep_idx}")
                # print(f"speaker_idx : {speaker_idx}")
                # print(f"utterance_idx : {utterance_idx}")
                # print(f"all_special_ids : {all_special_ids}")
                # print(f"enc_utterance.shape : {len(enc_utterance), enc_utterance[0].shape}")
                # print(f"enc_utterance : {enc_utterance}")
                    
                mean_utterance = torch.row_stack([torch.mean(i, 0) for i in enc_utterance])
                # print(f"mean : {mean_utterance.shape}")
                # ########################################################################################################
                ctr_topic_loss = self.topic_aware(enc_utterance=mean_utterance, # Mean Pooling한 utterance의 representation list
                                ctr_margin=1, # ctrastive learning 시, margin 값
                                cluster_mode=0, # 0=Kmeans, 1=Sequential, 2=DBSCAN
                                raw_data=raw_data
                                )
                ctr_speaker_loss = torch.zeros(1, device=device)
                # ########################################################################################################
            else:
                ctr_speaker_loss = torch.zeros(1, device=device)
                ctr_topic_loss = torch.zeros(1, device=device)

        elif ctr_mode == 3: # koBART + Spaeker-view + Topic-view
            if len(speaker_idx) > 1:
                # Speaker의 Encoder Representation -> Mean Pooling
                enc_speaker = [encoder_outputs[0][0][i[0]:i[1]] for i in speaker_idx]
                mean_speaker = torch.row_stack([torch.mean(i, 0) for i in enc_speaker])

                ############# 스피커 어웨어 부분 #################
                ctr_speaker_loss = self.speaker_aware(
                                        enc_speaker=mean_speaker, # speaker의 representation list
                                        ctr_margin=1, # ctrastive learning 시, margin 값
                                        speaker_input_ids=speaker_input_ids, # Dialogue 안 Speaker Token들의 input_ids list
                                        bench_speaker=0 # P01을 기준점 = 0번째 Speaker
                                    )
                # print(f"ctr_speaker_loss : {type(ctr_speaker_loss)}")

                # Utterance의 Encoder Representation -> Mean Pooling
                enc_utterance = [encoder_outputs[0][0][i[0]:i[1]] for i in utterance_idx]
                mean_utterance = torch.row_stack([torch.mean(i, 0) for i in enc_utterance])

                # ########################################################################################################
                ctr_topic_loss = self.topic_aware(
                                    enc_utterance=mean_utterance, # Mean Pooling한 utterance의 representation list
                                    ctr_margin=1, # ctrastive learning 시, margin 값
                                    cluster_mode=1, # 0=Kmeans, 1=Sequential, 2=DBSCAN
                                    raw_data=raw_data
                                )
                # print(f"ctr_topic_loss : {ctr_topic_loss}")
            else:
                ctr_speaker_loss = torch.zeros(1, device=device)
                ctr_topic_loss = torch.zeros(1, device=device)
        

        # for i in no_padding_len[1:]:
        #     enc = torch.cat([enc_utterance[0:i], enc_utterance[i+1:i+1]])
        #     print(f"enc.shape : {enc.shape}")
        #     enc_utterance = torch.cat((enc_utterance, enc), dim=0)
        #     print(f"enc_utterance : {enc_utterance.shape}")
        # enc_utterance = torch.cat([enc_utterance[0:0], enc_utterance[size:]])
        # print(f"enc_utterance.shape after : {enc_utterance.shape}")

        # for rep_speak, idx, i in zip(enc_speaker, speaker_input_ids, range(len(enc_speaker))):
        #     print(f"speaker_input_ids : {idx}")
        #     # print(f"rep_speak : {rep_speak}")
        #     self.speaker_aware(rep_speak, enc_speaker, idx, speaker_input_ids, i)
        
        # self.topic_aware(encoder_outputs[0])

        # decoder outputs consists of (dec_features, past_key_value, dec_hidden, dec_attn)
        decoder_outputs = self.decoder(
            input_ids=decoder_input_ids,
            attention_mask=decoder_attention_mask,
            encoder_hidden_states=encoder_outputs[0],
            encoder_attention_mask=attention_mask,
            head_mask=decoder_head_mask,
            cross_attn_head_mask=cross_attn_head_mask,
            past_key_values=past_key_values,
            inputs_embeds=decoder_inputs_embeds,
            use_cache=use_cache,
            output_attentions=output_attentions,
            output_hidden_states=output_hidden_states,
            return_dict=return_dict,
        )

        if not return_dict:
            return decoder_outputs + encoder_outputs

        # return Seq2SeqModelOutput(
        #     last_hidden_state=decoder_outputs.last_hidden_state,
        #     past_key_values=decoder_outputs.past_key_values,
        #     decoder_hidden_states=decoder_outputs.hidden_states,
        #     decoder_attentions=decoder_outputs.attentions,
        #     cross_attentions=decoder_outputs.cross_attentions,
        #     encoder_last_hidden_state=encoder_outputs.last_hidden_state,
        #     encoder_hidden_states=encoder_outputs.hidden_states,
        #     encoder_attentions=encoder_outputs.attentions,
        #     # ctr_speaker_loss=ctr_speaker_loss,
        # )

        return CustomSeq2SeqModelOutput(
            last_hidden_state=decoder_outputs.last_hidden_state,
            past_key_values=decoder_outputs.past_key_values,
            decoder_hidden_states=decoder_outputs.hidden_states,
            decoder_attentions=decoder_outputs.attentions,
            cross_attentions=decoder_outputs.cross_attentions,
            encoder_last_hidden_state=encoder_outputs.last_hidden_state,
            encoder_hidden_states=encoder_outputs.hidden_states,
            encoder_attentions=encoder_outputs.attentions,
            ctr_speaker_loss=ctr_speaker_loss,
            ctr_topic_loss=ctr_topic_loss,
        )

class BartForConditionalGeneration(BartPretrainedModel):
    base_model_prefix = "model"
    _keys_to_ignore_on_load_missing = [
        r"final_logits_bias",
        r"lm_head.weight",
        "encoder.embed_tokens.weight",
        "decoder.embed_tokens.weight",
    ]

    def __init__(self, config: BartConfig):
        super().__init__(config)
        self.model = BartModel(config)
        self.register_buffer("final_logits_bias", torch.zeros((1, self.model.shared.num_embeddings)))
        self.lm_head = nn.Linear(config.d_model, self.model.shared.num_embeddings, bias=False)

        # Initialize weights and apply final processing
        self.post_init()

    def get_encoder(self):
        return self.model.get_encoder()

    def get_decoder(self):
        return self.model.get_decoder()

    def resize_token_embeddings(self, new_num_tokens: int) -> nn.Embedding:
        new_embeddings = super().resize_token_embeddings(new_num_tokens)
        self._resize_final_logits_bias(new_num_tokens)
        return new_embeddings

    def _resize_final_logits_bias(self, new_num_tokens: int) -> None:
        old_num_tokens = self.final_logits_bias.shape[-1]
        if new_num_tokens <= old_num_tokens:
            new_bias = self.final_logits_bias[:, :new_num_tokens]
        else:
            extra_bias = torch.zeros((1, new_num_tokens - old_num_tokens), device=self.final_logits_bias.device)
            new_bias = torch.cat([self.final_logits_bias, extra_bias], dim=1)
        self.register_buffer("final_logits_bias", new_bias)

    def get_output_embeddings(self):
        return self.lm_head

    def set_output_embeddings(self, new_embeddings):
        self.lm_head = new_embeddings

    @add_start_docstrings_to_model_forward(BART_INPUTS_DOCSTRING)
    @replace_return_docstrings(output_type=Seq2SeqLMOutput, config_class=_CONFIG_FOR_DOC)
    @add_end_docstrings(BART_GENERATION_EXAMPLE)
    def forward(
        self,
        input_ids: torch.LongTensor = None,
        attention_mask: Optional[torch.Tensor] = None,
        decoder_input_ids: Optional[torch.LongTensor] = None,
        decoder_attention_mask: Optional[torch.LongTensor] = None,
        head_mask: Optional[torch.Tensor] = None,
        decoder_head_mask: Optional[torch.Tensor] = None,
        cross_attn_head_mask: Optional[torch.Tensor] = None,
        encoder_outputs: Optional[List[torch.FloatTensor]] = None,
        past_key_values: Optional[List[torch.FloatTensor]] = None,
        inputs_embeds: Optional[torch.FloatTensor] = None,
        decoder_inputs_embeds: Optional[torch.FloatTensor] = None,
        labels: Optional[torch.LongTensor] = None,
        use_cache: Optional[bool] = None,
        output_attentions: Optional[bool] = None,
        output_hidden_states: Optional[bool] = None,
        all_special_ids: Optional[List] = None,
        return_dict: Optional[bool] = None,
        raw_data: Optional[datasets.dataset_dict.DatasetDict] = None,
        ctr_mode: int = 0,
    ) -> Union[Tuple, Seq2SeqLMOutput]:
        r"""
        labels (`torch.LongTensor` of shape `(batch_size, sequence_length)`, *optional*):
            Labels for computing the masked language modeling loss. Indices should either be in `[0, ...,
            config.vocab_size]` or -100 (see `input_ids` docstring). Tokens with indices set to `-100` are ignored
            (masked), the loss is only computed for the tokens with labels in `[0, ..., config.vocab_size]`.

        Returns:
        """
        return_dict = return_dict if return_dict is not None else self.config.use_return_dict

        if labels is not None:
            if use_cache:
                logger.warning("The `use_cache` argument is changed to `False` since `labels` is provided.")
            use_cache = False
            if decoder_input_ids is None and decoder_inputs_embeds is None:
                decoder_input_ids = shift_tokens_right(
                    labels, self.config.pad_token_id, self.config.decoder_start_token_id
                )

        outputs = self.model(
            input_ids,
            attention_mask=attention_mask,
            decoder_input_ids=decoder_input_ids,
            encoder_outputs=encoder_outputs,
            decoder_attention_mask=decoder_attention_mask,
            head_mask=head_mask,
            decoder_head_mask=decoder_head_mask,
            cross_attn_head_mask=cross_attn_head_mask,
            past_key_values=past_key_values,
            inputs_embeds=inputs_embeds,
            decoder_inputs_embeds=decoder_inputs_embeds,
            use_cache=use_cache,
            output_attentions=output_attentions,
            output_hidden_states=output_hidden_states,
            return_dict=return_dict,
            all_special_ids=all_special_ids,
            raw_data=raw_data,
            ctr_mode=ctr_mode
        )

        # print(f"outputs[0] : {len(outputs[0])}")
        lm_logits = self.lm_head(outputs[0])
        lm_logits = lm_logits + self.final_logits_bias.to(lm_logits.device)

        masked_lm_loss = None
        if labels is not None:
            loss_fct = CrossEntropyLoss()
            masked_lm_loss = loss_fct(lm_logits.view(-1, self.config.vocab_size), labels.view(-1))

        if not return_dict:
            output = (lm_logits,) + outputs[1:]
            return ((masked_lm_loss,) + output) if masked_lm_loss is not None else output

        # return Seq2SeqLMOutput(
        #     loss=masked_lm_loss,
        #     # ctr_loss=outputs.ctr_speaker_loss,
        #     logits=lm_logits,
        #     past_key_values=outputs.past_key_values,
        #     decoder_hidden_states=outputs.decoder_hidden_states,
        #     decoder_attentions=outputs.decoder_attentions,
        #     cross_attentions=outputs.cross_attentions,
        #     encoder_last_hidden_state=outputs.encoder_last_hidden_state,
        #     encoder_hidden_states=outputs.encoder_hidden_states,
        #     encoder_attentions=outputs.encoder_attentions,
        # )

        # ctr_loss_sum = outputs.ctr_speaker_loss + outputs.ctr_topic_loss
        # print(f"ctr_loss : {ctr_loss_sum}")

        return CustomSeq2SeqLMOutput(
            loss=masked_lm_loss,
            ctr_loss=torch.mean(outputs.ctr_speaker_loss) + torch.mean(outputs.ctr_topic_loss),
            logits=lm_logits,
            past_key_values=outputs.past_key_values,
            decoder_hidden_states=outputs.decoder_hidden_states,
            decoder_attentions=outputs.decoder_attentions,
            cross_attentions=outputs.cross_attentions,
            encoder_last_hidden_state=outputs.encoder_last_hidden_state,
            encoder_hidden_states=outputs.encoder_hidden_states,
            encoder_attentions=outputs.encoder_attentions,
        )

    def prepare_inputs_for_generation(
        self,
        decoder_input_ids,
        past_key_values=None,
        attention_mask=None,
        decoder_attention_mask=None,
        head_mask=None,
        decoder_head_mask=None,
        cross_attn_head_mask=None,
        use_cache=None,
        encoder_outputs=None,
        **kwargs,
    ):
        # cut decoder_input_ids if past_key_values is used
        if past_key_values is not None:
            decoder_input_ids = decoder_input_ids[:, -1:]

        return {
            "input_ids": None,  # encoder_outputs is defined. input_ids not needed
            "encoder_outputs": encoder_outputs,
            "past_key_values": past_key_values,
            "decoder_input_ids": decoder_input_ids,
            "attention_mask": attention_mask,
            "decoder_attention_mask": decoder_attention_mask,
            "head_mask": head_mask,
            "decoder_head_mask": decoder_head_mask,
            "cross_attn_head_mask": cross_attn_head_mask,
            "use_cache": use_cache,  # change this to avoid caching (presumably for debugging)
        }

    def prepare_decoder_input_ids_from_labels(self, labels: torch.Tensor):
        return shift_tokens_right(labels, self.config.pad_token_id, self.config.decoder_start_token_id)

    @staticmethod
    def _reorder_cache(past_key_values, beam_idx):
        reordered_past = ()
        for layer_past in past_key_values:
            # cached cross_attention states don't have to be reordered -> they are always the same
            reordered_past += (
                tuple(past_state.index_select(0, beam_idx) for past_state in layer_past[:2]) + layer_past[2:],
            )
        return reordered_past