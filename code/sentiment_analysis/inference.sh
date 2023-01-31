python inference.py \
--output_dir ./models/train_dataset \
--fp16 \
--eval_data './data/비출판물 말뭉치_정제.csv' \
--model_name_or_path nlp04/korean_sentiment_analysis_kcelectra \
--per_device_train_batch_size 32 \
--per_device_eval_batch_size 32 \
--gradient_accumulation_steps 4 \
--num_train_epochs 5 \
--weight_decay 0.01 \
--warmup_ratio 0.1 \
--learning_rate 2e-5 \
--eval_steps 100 \
--logging_steps 100 \
--save_steps=1000 \
--load_best_model_at_end \
--evaluation_strategy steps \