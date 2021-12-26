import time
import datetime
from torch.nn import utils

import torchmetrics
import torch
from torch.utils.data import DataLoader
from transformers import  AdamW

from utils.utils import format_time, plot_confusion_matrix, plot_f1
from utils.utils import plot_loss
from loggers.neptune_logger import NeptuneLogger
import neptune.new as neptune


class MPTrainer():
    def __init__(self, batch_size, lr, n_epochs, ) -> None:
        self.batch_size = batch_size
        self.learning_rate = lr
        self.n_epochs = n_epochs

        self.logger = NeptuneLogger()

        self.metric_collection = torchmetrics.MetricCollection({

            'accuracy_micro' : torchmetrics.Accuracy(num_classes=23, multiclass=True, average='micro'),
            'accuracy_macro' : torchmetrics.Accuracy(num_classes=23, multiclass=True, average='macro'),
            'accuracy_weighted' : torchmetrics.Accuracy(num_classes=23, multiclass=True, average='weighted'),
            'accuracy_none' : torchmetrics.Accuracy(num_classes=23, multiclass=True, average='none'),

            'f1_micro' : torchmetrics.F1(num_classes=23, multiclass=True, average='micro'),
            'f1_macro' : torchmetrics.F1(num_classes=23, multiclass=True, average='macro'),
            'f1_weighted' : torchmetrics.F1(num_classes=23, multiclass=True, average='weighted'),
            'f1_none' : torchmetrics.F1(num_classes=23, multiclass=True, average='none'),

            'precision_micro' : torchmetrics.Precision(num_classes=23, multiclass=True, average='micro'),
            'precision_macro' : torchmetrics.Precision(num_classes=23, multiclass=True, average='macro'),
            'precision_weighted' : torchmetrics.Precision(num_classes=23, multiclass=True, average='weighted'),
            'precision_none' : torchmetrics.Precision(num_classes=23, multiclass=True, average='none'),

            'recall_micro' : torchmetrics.Recall(num_classes=23, multiclass=True, average='micro'),
            'recall_macro' : torchmetrics.Recall(num_classes=23, multiclass=True, average='macro'),
            'recall_weighted' : torchmetrics.Recall(num_classes=23, multiclass=True, average='weighted'),
            'recall_none' : torchmetrics.Recall(num_classes=23, multiclass=True, average='none')
        }) 
        
    def fit(self, model, train_dataset, val_dataset):
        
        params_info = {
            'learning_rate' : self.learning_rate,
            'batch_size' : self.batch_size,
            'n_epochs' : self.n_epochs
        }
        self.logger.run['params'] = params_info

        torch.cuda.empty_cache()
        #----------TRAINING

        # Measure the total training time for the whole run.
        total_t0 = time.time()

        epochs_train_loss = []
        epochs_val_loss = []
        epochs_train_f1 = []
        epochs_val_f1 = []

        epochs = self.n_epochs

        # Creation of Pytorch DataLoaders with shuffle=True for the traing phase
        train_dataloader = DataLoader(train_dataset, batch_size=self.batch_size, shuffle=True)
        validation_dataloader = DataLoader(val_dataset, batch_size=self.batch_size, shuffle=True)

        #Adam algorithm optimized for tranfor architectures
        optimizer = AdamW(model.parameters(), lr=self.learning_rate)

        # Scaler for mixed precision
        scaler = torch.cuda.amp.GradScaler()

        # Setup for training with gpu
        device = torch.device('cuda') if torch.cuda.is_available() else torch.device('cpu')
        model.to(device)

        # For each epoch...
        for epoch_i in range(0, epochs):
            
            # ========================================
            #               Training
            # ========================================
            
            # Perform one full pass over the training set.

            print("")
            print('======== Epoch {:} / {:} ========'.format(epoch_i + 1, epochs))
            print('Training...')

            # Measure how long the training epoch takes.
            t0 = time.time()

            # Reset the total loss for this epoch.
            total_train_loss = 0

            # Put the model into training mode: Dropout layers are active
            model.train()
            
            # For each batch of training data...
            for step, batch in enumerate(train_dataloader):

                # Progress update every 40 batches.
                if step % 10 == 0 and not step == 0:
                    # Compute time in minutes.
                    elapsed = format_time(time.time() - t0)
                    
                    # Report progress.
                    print('  Batch {:>5,}  of  {:>5,}.    Elapsed: {:}.'.format(step, len(train_dataloader), elapsed))

                # Unpack this training batch from the dataloader. 
                #
                #  copy each tensor to the GPU using the 'to()' method
                #
                # 'batch' contains three pytorch tensors:
                #   [0]: input ids 
                #   [1]: attention masks
                #   [2]: labels 
                b_input_ids = batch['input_ids'].to(device)
                b_input_mask = batch['attention_mask'].to(device)
                b_labels = batch['labels'].to(device)

                # clear any previously calculated gradients before performing a
                # backward pass
                model.zero_grad()  


                # Perform a forward pass in mixed precision
                with torch.cuda.amp.autocast():
                    outputs = model(b_input_ids, 
                                    attention_mask=b_input_mask, 
                                    labels=b_labels)
                
                loss = outputs[0]
                logits = outputs[1]

                # Move logits and labels to CPU
                logits = logits.detach().cpu()
                label_ids = b_labels.to('cpu')

                batch_metric = self.metric_collection.update(logits, label_ids)
                #print(batch_metric)

                # Perform a backward pass to compute the gradients in MIXED precision
                scaler.scale(loss).backward()

                # Accumulate the training loss over all of the batches so that we can
                # calculate the average loss at the end.
                total_train_loss += loss.item()

                # Unscales the gradients of optimizer's assigned params in-place before the gradient clipping
                scaler.unscale_(optimizer)

                # Clip the norm of the gradients to 1.0.
                # This helps and prevent the "exploding gradients" problem.
                torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)

                # Update parameters and take a step using the computed gradient in MIXED precision
                scaler.step(optimizer)
                scaler.update()


            # Compute the average loss over all of the batches.
            avg_train_loss = total_train_loss / len(train_dataloader)
            epochs_train_loss.append(avg_train_loss)

            final_metrics = self.metric_collection.compute()
            epochs_train_f1.append(final_metrics['f1_weighted'])
            
            # Measure how long this epoch took.
            training_time = format_time(time.time() - t0)

            print("")
            print("  Average training loss: {0:.3f}".format(avg_train_loss))
            print("  Training epoch took: {:}".format(training_time))

            # ========================================
            #               Validation
            # ========================================
            # After the completion of each training epoch, measure performance on
            # the validation set.

            print("")
            print("Running Validation...")

            self.metric_collection.reset()
            t0 = time.time()

            # Put the model in evaluation mode: the dropout layers behave differently
            model.eval()

            total_val_loss = 0

            # Evaluate data for one epoch
            for batch in validation_dataloader:
                
                # Unpack this training batch from our dataloader. 
                #
                # copy each tensor to the GPU using the 'to()' method
                #
                # 'batch' contains three pytorch tensors:
                #   [0]: input ids 
                #   [1]: attention masks
                #   [2]: labels 
                b_input_ids = batch['input_ids'].to(device)
                b_input_mask = batch['attention_mask'].to(device)
                b_labels = batch['labels'].to(device)
                
                # Tell pytorch not to bother with constructing the compute graph during
                # the forward pass, since this is only needed for training.
                with torch.no_grad():        

                    # Forward pass, calculate logits
                    # argmax(logits) = argmax(Softmax(logits))
                    outputs = model(b_input_ids, 
                                        attention_mask=b_input_mask,
                                        labels=b_labels)
                    loss = outputs[0]
                    logits = outputs[1]
                    
                # Accumulate the validation loss.
                total_val_loss += loss.item()

                # Move logits and labels to CPU
                logits = logits.detach().cpu()
                label_ids = b_labels.to('cpu')

                # metric on current batch
                batch_metric = self.metric_collection.update(logits.softmax(dim=1), label_ids)

            # Report the final metrics for this validation phase.
            # metric on all batches using custom accumulation from torchmetrics library

            final_metrics = self.metric_collection.compute()
            epochs_val_f1.append(final_metrics['f1_weighted'])

            self.logger.run['validation/' + str(epoch_i) + '/metrics'] = final_metrics
            print('VALIDATION: ')
            
            # Compute the average loss over all of the batches.
            avg_val_loss = total_val_loss / len(validation_dataloader)
            epochs_val_loss.append(avg_val_loss)
            
            # Measure how long the validation run took.
            validation_time = format_time(time.time() - t0)
            
            print("  Validation Loss: {0:.2f}".format(avg_val_loss))
            print("  Validation took: {:}".format(validation_time))

        loss_fig = plot_loss(epochs_train_loss, epochs_val_loss)
        f1_fig = plot_f1(epochs_train_f1, epochs_val_f1)
        self.logger.run["loss"].upload(neptune.types.File.as_image(loss_fig))
        self.logger.run["f1"].upload(neptune.types.File.as_image(f1_fig))
        print("")
        print("Training complete!")

        print("Total training took {:} (h:mm:ss)".format(format_time(time.time()-total_t0)))
    
    def test(self, model, test_dataset):
        # ========================================
        #               Test
        # ========================================
        # Measure performance on
        # the validation set.

        test_dataloader = DataLoader(test_dataset, batch_size=self.batch_size, shuffle=True)

        # Setup for testing with gpu
        device = torch.device('cuda') if torch.cuda.is_available() else torch.device('cpu')

        print("")
        print("Running Test...")

        self.metric_collection.reset()
        t0 = time.time()

        # Save prediction for confusion matrix
        pred = []

        # Put the model in evaluation mode: the dropout layers behave differently
        model.eval()

        total_test_loss = 0

        # Evaluate data for one epoch
        for batch in test_dataloader:
            
            # Unpack this training batch from our dataloader. 
            #
            # copy each tensor to the GPU using the 'to()' method
            #
            # 'batch' contains three pytorch tensors:
            #   [0]: input ids 
            #   [1]: attention masks
            #   [2]: labels 
            b_input_ids = batch['input_ids'].to(device)
            b_input_mask = batch['attention_mask'].to(device)
            b_labels = batch['labels'].to(device)
            
            # Tell pytorch not to bother with constructing the compute graph during
            # the forward pass, since this is only needed for training.
            with torch.no_grad():        

                # Forward pass, calculate logits
                # argmax(logits) = argmax(Softmax(logits))
                outputs = model(b_input_ids, 
                                        attention_mask=b_input_mask,
                                        labels=b_labels)
                loss = outputs[0]
                logits = outputs[1]
                
            # Accumulate the validation loss.
            total_test_loss += loss.item()

            # Move logits and labels to CPU
            logits = logits.detach().cpu()
            label_ids = b_labels.to('cpu')

            batch_pred = logits.softmax(dim=1)
            pred += batch_pred.argmax(dim=1)

            # metric on current batch

            batch_metric = self.metric_collection.update(batch_pred, label_ids)

        # Report the final metrics for this validation phase.
        # metric on all batches using custom accumulation from torchmetrics library

        test_metrics = self.metric_collection.compute()
        print(' Test metrics: ')

        self.logger.run['test/metrics'] = test_metrics
        # Compute the average loss over all of the batches.
        avg_test_loss = total_test_loss / len(test_dataloader)

        self.logger.run['test/loss'] = avg_test_loss

        # Measure how long the validation run took.
        test_time = format_time(time.time() - t0)

        print("  Test Loss: {0:.2f}".format(avg_test_loss))
        print("  Test took: {:}".format(test_time))

        #torch.save(model.state_dict(), './')

        y_true = test_dataset[:]['labels']

        cm = plot_confusion_matrix(y_true, pred, test_dataset.LABELS)

        self.logger.run["confusion_matrix"].upload(neptune.types.File.as_image(cm))
                
    