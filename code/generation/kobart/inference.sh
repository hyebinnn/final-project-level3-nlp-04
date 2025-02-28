python inference.py \
--output_dir ./models/inference_output \
--do_predict \
--eval_data ./dataset/diary_test.csv \
--fp16 \
--model_name_or_path ./models/total_comment_emotion \
--per_device_train_batch_size 8 \
--per_device_eval_batch_size 128 \
--num_train_epochs 5 \
--weight_decay 0.01 \
--warmup_ratio 0.1 \
--learning_rate 5.6e-5 \
--eval_steps 1000 \
--logging_steps 100 \
--save_steps=1000 \
--save_total_limit=3 \
--predict_with_generate=True \
--load_best_model_at_end \
--evaluation_strategy steps