import tensorflow as tf
from tensorflow import keras
import random

from .quantize import quantize

class CustomModelList(list):
    def fed_avg(self, x, y, metric, central_server):
      trainable_vars = central_server.model.trainable_variables
      loss_avg = 0
      sca_metric_avg = 0
      for i, model in enumerate(self):
        train_results = model.train_step(x[int(i*len(x)/len(self)):int((i+1)*len(x)/len(self))],y[int(i*len(x)/len(self)):int((i+1)*len(x)/len(self))], metric)
        loss_avg += train_results[1]
        sca_metric_avg += train_results[2]
        # Averaging gradients
        if(i % len(self) == 0):
          gradient_avg = train_results[0]
        else:
          for j in range(len(train_results[0])):
            gradient_avg[j] += train_results[0][j]
      loss_avg = loss_avg / len(self)
      sca_metric_avg = sca_metric_avg / len(self)
      for i in range(len(gradient_avg)):
        gradient_avg[i] = gradient_avg[i] / len(self)
      ## Update weights
      for i, model in enumerate(self):
        self[i].model.set_weights(central_server.model.get_weights())
        model.optimizer.apply_gradients(zip(gradient_avg, self[i].model.trainable_variables))
      central_server.optimizer.apply_gradients(zip(gradient_avg, trainable_vars))
      # # Update metrics (includes the metric that tracks the loss)
      # # Return a dict mapping metric names to current value
      return loss_avg, sca_metric_avg

    def pfed_avg(self, x, y, metric, central_server, gradient_avg, L, marker):
      trainable_vars = central_server.model.trainable_variables
      loss_avg = 0
      sca_metric_avg = 0
      for i, model in enumerate(self):
        train_results = model.train_step(x[int(i*len(x)/len(self)):int((i+1)*len(x)/len(self))],y[int(i*len(x)/len(self)):int((i+1)*len(x)/len(self))], metric)
        model.optimizer.apply_gradients(zip(train_results[0], self[i].model.trainable_variables))
        loss_avg += train_results[1]
        sca_metric_avg += train_results[2]
        # Averaging gradients
        if i % len(self) == 0 and marker % L == 0:
          gradient_avg = train_results[0]
        else:
          for j in range(len(train_results[0])):
            gradient_avg[j] += train_results[0][j]
      loss_avg = loss_avg / len(self)
      sca_metric_avg = sca_metric_avg / len(self)
      
      ## Update weights
      if (marker + 1) % L == 0:
        for i in range(len(gradient_avg)):
          gradient_avg[i] = gradient_avg[i] / (len(self))
        central_server.optimizer.apply_gradients(zip(gradient_avg, trainable_vars))
        for i, model in enumerate(self):
          self[i].model.set_weights(central_server.model.get_weights())
          # model.optimizer.apply_gradients(zip(gradient_avg, self[i].model.trainable_variables))
        
      # # Update metrics (includes the metric that tracks the loss)
      # # Return a dict mapping metric names to current value
      return loss_avg, sca_metric_avg, gradient_avg

    def rfed_avg(self, x, y, r_central_server, prob):
      trainable_vars = r_central_server.model.trainable_variables
      loss_avg = 0
      sca_metric_avg = 0
      p = prob
      random_list = randomize_list(len(self), p)
      randomized_models = []
      for i, model in enumerate(self):
        if(random_list[i] != 0):
          train_results = model.train_step(x[int(i*len(x)/len(self)):int((i+1)*len(x)/len(self))],y[int(i*len(x)/len(self)):int((i+1)*len(x)/len(self))], 'R')
          randomized_models.append(self[i].model)
          # Averaging gradients
          if(self[i].model == randomized_models[0]):
            gradient_avg = train_results[0]
          else:
            for j in range(len(train_results[0])):
              gradient_avg[j] = gradient_avg[j] + train_results[0][j]
        else:
          train_results = model.train_step(x[int(i*len(x)/len(self)):int((i+1)*len(x)/len(self))],y[int(i*len(x)/len(self)):int((i+1)*len(x)/len(self))], 'R')
        loss_avg += train_results[1]
        sca_metric_avg += train_results[2]
        
        # if(i % len(randomized_models) == 0):
        #   gradient_avg = train_results[0]
        # else:
        #   for j in range(len(train_results[0])):
        #     gradient_avg[j] = gradient_avg[j] + train_results[0][j]
      loss_avg = loss_avg / len(self)
      sca_metric_avg = sca_metric_avg / len(self)
      if(len(randomized_models) != 0):
        for i in range(len(gradient_avg)):
          gradient_avg[i] = gradient_avg[i] / len(randomized_models)
        ## Update weights
        for i, model in enumerate(self):
          self[i].model.set_weights(r_central_server.model.get_weights())
          model.optimizer.apply_gradients(zip(gradient_avg, self[i].model.trainable_variables))
        r_central_server.optimizer.apply_gradients(zip(gradient_avg, trainable_vars))
      # # Update metrics (includes the metric that tracks the loss)
      # # Return a dict mapping metric names to current value
      return loss_avg, sca_metric_avg


class CustomModel(keras.Model):
    def __init__(self, model):
        super(CustomModel, self).__init__()
        self.model = model
      
    def train_step(self, x, y, metric):
      loss_fn = keras.losses.SparseCategoricalCrossentropy()
        # Unpack the data. Its structure depends on your model and
        # on what you pass to `fit()`.
      with tf.GradientTape() as tape:
        y_pred = self.model(x, training=False)  # Forward pass
        # Compute the loss value
        # (the loss function is configured in `compile()`)
        loss = loss_fn(y, y_pred)
      # Compute gradients
      trainable_vars = self.model.trainable_variables
      gradients = tape.gradient(loss, trainable_vars)
      # # Update weights

      # import pdb; pdb.set_trace()
      # self.optimizer.apply_gradients(zip(gradients, trainable_vars))
      # # Update metrics (includes the metric that tracks the loss)
      result_metric = 0
      
      metric.update_state(y, y_pred)
      result_metric = metric.result().numpy()

      # # Return a dict mapping metric names to current value

      return gradients, loss.numpy(), result_metric
    
    def p_train_step(self, x, y, metric):
      loss_fn = keras.losses.SparseCategoricalCrossentropy()
        # Unpack the data. Its structure depends on your model and
        # on what you pass to `fit()`.
      with tf.GradientTape() as tape:
        y_pred = self.model(x, training=True)  # Forward pass
        # Compute the loss value
        # (the loss function is configured in `compile()`)
        loss = loss_fn(y, y_pred)
      # Compute gradients
      trainable_vars = self.model.trainable_variables
      gradients = tape.gradient(loss, trainable_vars)
      
      # Update weights
      #self.optimizer.apply_gradients(zip(gradients, trainable_vars))
      
      # Update metrics (includes the metric that tracks the loss)
      result_metric = 0
      
      metric.update_state(y, y_pred)
      result_metric = metric.result().numpy()

      # # Return a dict mapping metric names to current value
      return gradients, loss.numpy(), result_metric
  

def randomize_list(n, p):
  select_list = [0, 1]
  distri = [1-p, p]
  random_list = []
  for i in range(n):
    random_list.append(random.choices(select_list, distri)[0])
  return random_list