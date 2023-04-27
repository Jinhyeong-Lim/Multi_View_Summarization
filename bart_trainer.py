from transformers import BartTokenizerFast
from datasets import load_dataset
from dataclasses import dataclass, field
from typing import Optional
from transformers import DataCollatorForSeq2Seq
import evaluate
import numpy as np
from transformers import Seq2SeqTrainingArguments, Seq2SeqTrainer, HfArgumentParser
from bartmodel import BartForConditionalGeneration
import numpy as np
import re
import wandb

@dataclass
class RunArguments:
    model_name: str = field(default="facebook/bart-large")
    data_name: str = field(default="samsum")
    ctr_mode: int = field(default=3)
    lamda: Optional[float] = field(default=0.08)
    batch_size: int = field(default=8)
    gpu_use: str = field(default="0")
    set_seed: int = field(default=100)
    cluster_mode: int = field(default=1)

parser = HfArgumentParser((Seq2SeqTrainingArguments, RunArguments))
training_args, run_args = parser.parse_args_into_dataclasses()

ctr_mode = run_args.ctr_mode
lamda = run_args.lamda
model_name = run_args.model_name # "facebook/bart-large"
batch_size = run_args.batch_size
gpu_use = run_args.gpu_use
set_seed = run_args.set_seed
cluster_mode = run_args.cluster_mode

# Define the preprocessing function
def preprocess_function(examples):
    dialogue = ["<sep>" + re.sub("\r\n", "<sep>", i) for i in examples["dialogue"]]
    model_inputs = tokenizer(dialogue, max_length=1024, truncation=True)
    labels = tokenizer(text_target=examples["summary"], max_length=128, truncation=True)
    model_inputs["labels"] = labels["input_ids"]
    return model_inputs

def compute_metrics(eval_pred):
    # metric with ROUGE Scores
    predictions, labels = eval_pred
    decoded_preds = tokenizer.batch_decode(predictions, skip_special_tokens=True)
    labels = np.where(labels != -100, labels, tokenizer.pad_token_id)
    decoded_labels = tokenizer.batch_decode(labels, skip_special_tokens=True)

    # Check Generated Summary
    cnt=0
    for preds, labels in zip(decoded_preds, decoded_labels):
        print(f"=======================<decoded_preds {cnt}>======================")
        print(f"decoded_preds : {preds}")
        print(f"=======================<decoded_labels {cnt}>======================")
        print(f"decoded_labels : {labels}")
        cnt += 1
    
    result = rouge.compute(predictions=decoded_preds, references=decoded_labels, tokenizer=lambda x: tokenizer.tokenize(x), use_stemmer=True)
    print(f"rouge : {result}")
    prediction_lens = [np.count_nonzero(pred != tokenizer.pad_token_id) for pred in predictions]
    result["gen_len"] = np.mean(prediction_lens)

    return {k: round(v, 4) for k, v in result.items()}

# Custom BartTrainer
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
                        ctr_mode=ctr_mode,
                        cluster_mode=cluster_mode
                        )
        
        # Save past state if it exists
        # TODO: this needs to be fixed and made cleaner later.
        if self.args.past_index >= 0:
            self._past = outputs[self.args.past_index]

        if labels is not None:
            loss = self.label_smoother(outputs, labels)
        else:
            if isinstance(outputs, dict) and "loss" not in outputs:
                raise ValueError(
                    "The model did not return a loss from the inputs, only the following keys: "
                    f"{','.join(outputs.keys())}. For reference, the inputs it received are {','.join(inputs.keys())}."
                )
            # We don't use .loss here since the model may return tuples instead of ModelOutput.
            loss = outputs["loss"] if isinstance(outputs, dict) else outputs[0]
        
        # final_loss : generation loss + contrastive loss
        final_loss = loss + lamda * outputs.ctr_loss
        return (final_loss, outputs) if return_outputs else final_loss

# We use wandb logger: https://wandb.ai/site.
if training_args.local_rank == 0:  # only on main process
    # Initialize wandb run
    wandb.login()
    wandb.init(project="Multi-View_Dialogue_Summary", name=training_args.run_name)

# dataset is SAMSum
datasets = load_dataset(run_args.data_name) # "samsum")

tokenizer = BartTokenizerFast.from_pretrained(model_name)
model = BartForConditionalGeneration.from_pretrained(model_name)

print(f"before tokenizer.vocab_size : {tokenizer.vocab_size}")
num_add_token = tokenizer.add_special_tokens({"additional_special_tokens":["<sep>", ":"]})

# Preprocessing data
tokenized_data = datasets.map(preprocess_function, batched=True)

print(f"tokenized_data : {tokenized_data}")
# Resize model's token embedding numbers because of special tokens
model.resize_token_embeddings(tokenizer.vocab_size + num_add_token)
data_collator = DataCollatorForSeq2Seq(tokenizer=tokenizer, model=model)
rouge = evaluate.load("rouge")


# Arguments for Trainer
training_args = Seq2SeqTrainingArguments(
    output_dir="test_save",
    per_device_train_batch_size=batch_size,
    per_device_eval_batch_size=batch_size,
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

# Check the current device
print(f"training_args.device : {training_args.device}")

# Let's train!
trainer = BartTrainer(
    model=model, # all_special_ids = train[1]
    args=training_args,
    train_dataset=tokenized_data['train'],
    eval_dataset=tokenized_data['validation'],
    tokenizer=tokenizer,
    data_collator=data_collator,
    compute_metrics=compute_metrics,
    all_special_ids=tokenizer.all_special_ids,
    raw_data=tokenized_data['train']
)
trainer.train()

# Let's predict!
predict_results = trainer.predict(
            tokenized_data['test'],
            metric_key_prefix=" ",
            max_length=80,
            num_beams=6,
            length_penalty=1.0,
            no_repeat_ngram_size=3
        )

# Let's check the metric scores of predict!
metrics = predict_results.metrics
trainer.log_metrics("predict", metrics)
trainer.save_metrics("predict", metrics)