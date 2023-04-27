import torch
from transformers import BartTokenizerFast
from datasets import load_dataset
from transformers import DataCollatorForSeq2Seq, AutoModelForSeq2SeqLM
import evaluate
import numpy as np
from transformers import Seq2SeqTrainingArguments, Seq2SeqTrainer
from bartmodel import BartModel, BartForConditionalGeneration
import numpy as np
import re
import random
from evaluate import evaluator

# import os
# os.environ["CUDA_DEVICE_ORDER"] = "PCI_BUS_ID"
# os.environ["CUDA_VISIBLE_DEVICES"] = "1"
# device = torch.device('cuda:1')
# torch.cuda.set_device(device)
# print(f"cuda : {torch.cuda.current_device()}")
ctr_mode = 3
lamda = 0.07
model_name = "facebook/bart-large"
# model_name = "/root/bart_customize/test_save/checkpoint-8000"

# datasets = load_dataset("csv", data_files={"train": "data/train.csv", "valid": "data/valid.csv", "test": "data/test.csv"})
datasets = load_dataset("samsum")

tokenizer = BartTokenizerFast.from_pretrained(model_name)
model = BartForConditionalGeneration.from_pretrained(model_name)

print(f"before tokenizer.vocab_size : {tokenizer.vocab_size}")
num_add_token = tokenizer.add_special_tokens({"additional_special_tokens":["<sep>", ":"]})

# preprocess_datas = DataPreProcess(data_file_type="csv",
#                              train_files="data/train.csv",
#                              valid_files="data/valid.csv",
#                              test_files="data/test.csv",
#                              model_name=model_name)
# train, valid, test, tokenizer = preprocess_datas(num_dialogue=5)

# print(f"tokenizer.all_special_ids, num_add_token : {tokenizer.vocab_size, num_add_token}")
# special_ids = num_add_token

def preprocess_function(examples):
    dialogue = ["<sep>" + re.sub("\r\n", "<sep>", i) for i in examples["dialogue"]]
    # print(f"dialogue : {dialogue}")
    # preprocessing_dialog, turn_document = [], []
    # whole_speakers = []
    # preprocessing_dialog = [re.sub("\r\n", "<sep>", dialog) for dialog in dialogue]
    # print(f"preprocessing_dialog : {preprocessing_dialog}")

    # for dialog in preprocessing_dialog:
    #     turn = ""
    #     sep_turn = dialog.split("<sep>")
    #     # print(f"sep_turn : {sep_turn}")
    #     speaker_tok = []
    #     for sep in sep_turn:
    #         speaker_utter = sep.split(": ")
    #         speaker_tok.append(re.sub("[^\uAC00-\uD7A30-9a-zA-Z\s]", "", speaker_utter[0]))
    #     speakers = list(set(speaker_tok))
    #     whole_speakers.append(speakers)
    #     ppdialog = []
    #     for sep in sep_turn:
    #         sep = re.sub("[\(\)-=\<\>]", "", sep)
    #         for i, j in zip(speakers, ["P01:", "P02:", "P03:", "P04:", "P05:", "P06:", "P07:", "P08:", "P09:", "P10:", "P11:", "P12:", "P13:", "P14:", "P15:"]):
    #             if sep.find(i) != -1:
    #                 ppdialog.append(re.sub(i, "<sep>"+j, sep))
    #     for t in ppdialog:
    #         turn += t
    #     # print(f"turn : {turn}")
    #     turn_document.append(turn)
    
    # summ_prepro = []
    # for summ, cnt in zip(examples["summary"], range(len(examples["summary"]))):
    #     # print(f"whole_speakers[cnt] : {whole_speakers[cnt]}")
    #     for i, j in zip(whole_speakers[cnt], ["P01", "P02", "P03", "P04", "P05", "P06", "P07", "P08", "P09", "P10", "P11", "P12", "P13", "P14", "P15"]):
    #         summ_i = summ.lower()
    #         find_i = i.lower()
    #         if summ_i.find(find_i) != -1:
    #             summ = re.sub(i, j, summ)
    #     summ_prepro.append(summ)
    #     # print(f"summ_prepro : {summ_prepro}")
    
    # inputs = [doc for doc in turn_document]
    # # print(f"input : {inputs}")
    # model_inputs = tokenizer(inputs, max_length=1024, truncation=True)
    # labels = tokenizer(text_target=summ_prepro, max_length=128, truncation=True)
    # model_inputs["labels"] = labels["input_ids"]
    # return model_inputs

    # inputs, summary = [], []
    # speaker_tokens = ["P01:", "P02:", "P03:", "P04:", "P05:", "P06:", "P07:", "P08:", "P09:"]

    # # print(f"x['dialogue'].split('<sep>') : {examples['dialogue'].split('<sep>')}")

    # # P01, P02, P03 등 작은 숫자 Speaker가 더 자주 등장 -> Speaker 토큰을 랜덤하게 전처리(P01, P02, P03 -> P02, P05, P09 등으로)
    # for i, j in zip(examples['dialogue'], examples["summary"]):

    #     # <sep> 기준으로 turn 나누기
    #     turn = i.split("<sep>")
    #     # old_speakers_token : 바꿔줄 기존 Speaker Token 목록
    #     print(f"turn : {turn}")
    #     old_speakers_token = list(set([re.sub("[^P01]|[^P02]|[^P03]|[^P04]|[^P05]|[^P06]|[^P07]|[^P08]|[^P09]", "", t) for t in turn])) # P02|P03|P04|P05|P06|P07|P08|P09
    #     print(f"old_speakers_token : {old_speakers_token}")
    #     # new_speakers_token : 바꿀 랜덤한  Speaker Token 목록
    #     new_speakers_token = [re.sub("[:]", "", j) for j in random.sample(speaker_tokens, k=(len(old_speakers_token)%10))]
    #     # Turn에 Speaker Token 랜덤하게 바꿔 넣기
    #     dialogue_turn = [re.sub(old, new, t) for t in turn for old, new in zip(old_speakers_token, new_speakers_token) if old in t]

    #     # Speaker Token을 섞고 <sep> Token 붙이기
    #     after_dialogue = ""
    #     for t in dialogue_turn:
    #         after_dialogue += "<sep>"+t
        
    #     assert len(after_dialogue) > 0, f"after_dialogue : {after_dialogue}, turn : {turn}, old_speakers_token : {old_speakers_token}"
    #     print(f"after_dialogue : {after_dialogue}")
    #     # print(f"after_dialogue : {len(after_dialogue)}")
    #     # print(f"summary : {len(j)}")

    #     # inputs : 전처리한 Dialogue를 tokenizing -> max_length=1024, truncation=True
    #     inputs.append(after_dialogue)
    #     summary.append(j)
    model_inputs = tokenizer(dialogue, max_length=1024, truncation=True)
    labels = tokenizer(text_target=examples["summary"], max_length=128, truncation=True)
    model_inputs["labels"] = labels["input_ids"]
    return model_inputs

    # inputs = [doc for doc in examples["dialogue"]]
    # model_inputs = tokenizer(inputs, max_length=1024, truncation=True)
    # labels = tokenizer(text_target=examples["summary"], max_length=128, truncation=True)
    # model_inputs["labels"] = labels["input_ids"]
    # return model_inputs

def filter_by_num_words(example):
    return len(example["dialogue"].split("<sep>")) > 7

# filter_datasets = datasets.filter(filter_by_num_words)
tokenized_data = datasets.map(preprocess_function, batched=True)
print(f"tokenized_data : {tokenized_data}")
# Model special_token 추가한 수로 vocab_size 맞춰주기
model.resize_token_embeddings(tokenizer.vocab_size + num_add_token)
data_collator = DataCollatorForSeq2Seq(tokenizer=tokenizer, model=model)
rouge = evaluate.load("rouge")

# task_evaluator = evaluator("summarization")
# results = task_evaluator.compute(
#     model_or_pipeline=model_name,
#     data=tokenized_data['valid'],
#     input_column="dialogue",
#     label_column="summary",
#     tokenizer=tokenizer,
#     metric="rouge",
# )

def compute_metrics(eval_pred):
    predictions, labels = eval_pred
    decoded_preds = tokenizer.batch_decode(predictions, skip_special_tokens=True)
    labels = np.where(labels != -100, labels, tokenizer.pad_token_id)
    decoded_labels = tokenizer.batch_decode(labels, skip_special_tokens=True)
    cnt=0
    for preds, labels in zip(decoded_preds, decoded_labels):
        print(f"=======================<decoded_preds {cnt}>======================")
        print(f"decoded_preds : {preds}")
        print(f"=======================<decoded_labels {cnt}>======================")
        print(f"decoded_labels : {labels}")
        cnt += 1
    # breakpoint()
    result = rouge.compute(predictions=decoded_preds, references=decoded_labels, tokenizer=lambda x: tokenizer.tokenize(x), use_stemmer=True)
    print(f"rouge : {result}")
    prediction_lens = [np.count_nonzero(pred != tokenizer.pad_token_id) for pred in predictions]
    result["gen_len"] = np.mean(prediction_lens)

    return {k: round(v, 4) for k, v in result.items()}

training_args = Seq2SeqTrainingArguments(
    output_dir="test_save",
    per_device_train_batch_size= 8,
    per_device_eval_batch_size= 8,
    save_total_limit=3,
    evaluation_strategy="steps",
    gradient_accumulation_steps= 1,
    gradient_checkpointing=True,
    learning_rate= 2e-5,
    max_steps=10000,
    eval_steps=1000,
    save_steps=1000,
    weight_decay= 0.1,
    label_smoothing_factor=0.1,
    predict_with_generate=True,
    fp16=True,
    seed=1
)

class BartTrainer(Seq2SeqTrainer):
    def __init__(self, all_special_ids, raw_data, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.all_special_ids = all_special_ids
        self.raw_data = raw_data

    def compute_loss(self, model, inputs, return_outputs=False):
        # implement custom logic here
        if self.label_smoother is not None and "labels" in inputs:
            labels = inputs.pop("labels")
        else:
            labels = None
        outputs = model(**inputs, 
                        all_special_ids=self.all_special_ids, 
                        raw_data=self.raw_data,
                        ctr_mode=ctr_mode
                        )
        
        # Save past state if it exists
        # TODO: this needs to be fixed and made cleaner later.
        if self.args.past_index >= 0:
            self._past = outputs[self.args.past_index]

        if labels is not None:
            #if unwrap_model(model)._get_name() in MODEL_FOR_CAUSAL_LM_MAPPING_NAMES.values():
            #    loss = self.label_smoother(outputs, labels, shift_labels=True)
            #else:
            loss = self.label_smoother(outputs, labels)
        else:
            if isinstance(outputs, dict) and "loss" not in outputs:
                raise ValueError(
                    "The model did not return a loss from the inputs, only the following keys: "
                    f"{','.join(outputs.keys())}. For reference, the inputs it received are {','.join(inputs.keys())}."
                )
            # We don't use .loss here since the model may return tuples instead of ModelOutput.
            loss = outputs["loss"] if isinstance(outputs, dict) else outputs[0]

        # print(f"before ctr_loss : {torch.mean(outputs.ctr_loss)}")
        
        
        final_loss = loss + lamda * outputs.ctr_loss
        # print(f"ctr_loss : {final_loss} loss : {loss}, ctr : {torch.mean(outputs.ctr_loss)}")
        # loss += outputs["ctr_loss"]
        # print(f"outputs : {type(outputs.ctr_loss.item())}, loss : {loss}, loss+outputs.ctr_loss : {type(loss+outputs.ctr_loss.item())}")
        # # loss += outputs.ctr_loss[0]
        # final_loss = loss + outputs.ctr_loss.item()
        # print(f"loss : {loss}")
        # print(f"loss : {loss}, ctr_loss : {outputs['ctr_loss']}")
        return (final_loss, outputs) if return_outputs else final_loss

print(f"training_args.device : {training_args.device}")

trainer = BartTrainer(
    model=model, # all_special_ids = train[1]
    args=training_args,
    train_dataset=tokenized_data['train'],
    eval_dataset=tokenized_data['validation'],
    # eval_dataset=tokenized_data['valid'],
    tokenizer=tokenizer,
    data_collator=data_collator,
    # compute_metrics=results,
    compute_metrics=compute_metrics,
    all_special_ids=tokenizer.all_special_ids,
    raw_data=tokenized_data['train']
)
trainer.train()

predict_results = trainer.predict(
            tokenized_data['test'],
            metric_key_prefix=" ",
            max_length=80,
            num_beams=6,
            length_penalty=1.0,
            no_repeat_ngram_size=3
        )

metrics = predict_results.metrics
trainer.log_metrics("predict", metrics)
trainer.save_metrics("predict", metrics)