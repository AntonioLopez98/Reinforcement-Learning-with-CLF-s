import numpy as np
import matplotlib.pyplot as plt
import math
import gym
from gym import spaces
import time
import itertools
import argparse
import datetime
import random
import torch
from sac import SAC
from replay_memory import ReplayMemory
from torch.utils.tensorboard import SummaryWriter
import scipy.io as sio
import tensorflow as tf
import matplotlib.pyplot as plt
import seaborn as sns
import matplotlib.patches as mpatches
import pandas as pd

parser = argparse.ArgumentParser(description='PyTorch Soft Actor-Critic Args')
parser.add_argument('--env-name', default="HalfCheetah-v2",
                    help='Mujoco Gym environment (default: HalfCheetah-v2)')
parser.add_argument('--policy', default="Gaussian",
                    help='Policy Type: Gaussian | Deterministic (default: Gaussian)')
parser.add_argument('--eval', type=bool, default=True,
                    help='Evaluates a policy a policy every 10 episode (default: True)')
parser.add_argument('--gamma', type=float, default=0.95, metavar='G',
                    help='discount factor for reward (default: 0.99)')
parser.add_argument('--tau', type=float, default=0.005, metavar='G',
                    help='target smoothing coefficient(τ) (default: 0.005)')
parser.add_argument('--lr', type=float, default=0.0003, metavar='G',
                    help='learning rate (default: 0.0003)')
parser.add_argument('--alpha', type=float, default=0.2, metavar='G',
                    help='Temperature parameter α determines the relative importance of the entropy\
                            term against the reward (default: 0.2)')
parser.add_argument('--automatic_entropy_tuning', type=bool, default=False, metavar='G',
                    help='Automaically adjust α (default: False)')
parser.add_argument('--seed', type=int, default=123456, metavar='N',
                    help='random seed (default: 123456)')
parser.add_argument('--batch_size', type=int, default=256, metavar='N',
                    help='batch size (default: 256)')
parser.add_argument('--num_steps', type=int, default=60000, metavar='N',
                    help='maximum number of steps (default: 1000000)')
parser.add_argument('--hidden_size', type=int, default=256, metavar='N',
                    help='hidden size (default: 256)')
parser.add_argument('--updates_per_step', type=int, default=1, metavar='N',
                    help='model updates per simulator step (default: 1)')
parser.add_argument('--start_steps', type=int, default=1000, metavar='N',
                    help='Steps sampling random actions (default: 10000)')
parser.add_argument('--target_update_interval', type=int, default=1, metavar='N',
                    help='Value target update per no. of updates per step (default: 1)')
parser.add_argument('--replay_size', type=int, default=1000000, metavar='N',
                    help='size of replay buffer (default: 10000000)')
parser.add_argument('--cuda', action="store_true",
                    help='run on CUDA (default: False)')
parser.add_argument('--max_episode_length', type=int, default=1000, metavar='N',
					help='max episode length (default: 3000)')
args = parser.parse_args()
sigma=[]

# Training constants
MAX_STEER = np.pi
MAX_SPEED = 10.0
MIN_SPEED = 0.
THRESHOLD_DISTANCE_2_GOAL = 0.02
MAX_X = 3.
MAX_Y = 3.
THETA0 = np.pi/4

# Vehicle parameters
LENGTH = 0.45  # [m]
WIDTH = 0.2  # [m]
BACKTOWHEEL = 0.1  # [m]
WHEEL_LEN = 0.03  # [m]
WHEEL_WIDTH = 0.02  # [m]
TREAD = 0.07  # [m]
WB = 0.25  # [m]

#import matlab data
'''V= sio.loadmat('V_gamma03.mat')
V_1 = tf.convert_to_tensor(V['V_2'])

dim1=V_1.shape[0]
dim2=V_1.shape[1]
dim3=V_1.shape[2]
max_1=3
max_2=3
max_3=np.pi
x_1=np.linspace(-max_1,max_1,dim1)
x_2=np.linspace(-max_2,max_2,dim2)
x_3=np.linspace(-max_3,max_3,dim3)
'''

show_animation = True

class DubinGym(gym.Env):

	def __init__(self, start_point):
		super(DubinGym,self).__init__()
		metadata = {'render.modes': ['console']}
		self.action_space = spaces.Box(np.array([0., -1.57]), np.array([1., 1.57]), dtype = np.float32) # Action space for [throttle, steer]
		low = np.array([-1.,-1.,-4.]) # low range of observation space
		high = np.array([1.,1.,4.]) # high range of observation space
		self.observation_space = spaces.Box(low, high, dtype=np.float32) # Observation space for [x, y, theta]
		self.target = [0./MAX_X, 0./MAX_Y, 1.57] # Final goal point of trajectory
		self.pose = [start_point[0]/MAX_X, start_point[1]/MAX_Y, start_point[2]] # Current pose of car
		self.action = [0., 0.] # Action 
		self.traj_x = [self.pose[0]*MAX_X] # List of tracked trajectory for rendering
		self.traj_y = [self.pose[1]*MAX_Y] # List of tracked trajectory for rendering
		self.traj_yaw = [self.pose[2]] # List of tracked trajectory for rendering
		
	"""
	Redundant functions
	"""
	"""
	def getAngularSeperationAndIdx(self):
		prev_idx = self.closest_idx
		self.next_index()
		idx_nxt = self.closest_idx
		if idx_nxt != prev_idx : #Update Look ahead only if closest index changes
			if idx_nxt + self.n_waypoints > len(self.waypoints):
				self.look_ahead = self.waypoints[idx_nxt: ]
			else:
				self.look_ahead = self.waypoints[idx_nxt: idx_nxt + self.n_waypoints]
			print(self.look_ahead)
		#self.waypoints[idx_nxt]
		a = self.get_heading(self.pose,self.waypoints[idx_nxt])
		b = self.pose[2]

		prev_ind = idx_nxt #Save previous index

		#print('heading',a)
		return abs(a-b), idx_nxt
	
	def getClosestIndex(self):
		closestDist = 10000
		idx = 0
		idxCount = 0
		for point in self.waypoints:
			idxCount = idxCount + 1
			x1 = [self.pose[0],self.pose[1]]
			if(self.get_distance(x1,[point[0],point[1]])<closestDist):
				closestDist = self.get_distance(x1,[point[0],point[1]])
				idx = idxCount
				print('closestDist',closestDist)

		return idx

	def get_closest_idx(self):
		self.d_to_waypoints = np.zeros(len(self.waypoints))

		for i in range(len(self.waypoints)):
			self.d_to_waypoints[i] = self.get_distance(self.waypoints[i], self.pose)

		prev_ind, next_ind = np.argpartition(self.d_to_waypoints, 2)[:2]
		self.closest_idx = max(prev_ind, next_ind)
		# return max(prev_ind, next_ind)

	def get_look_ahead(self):
		if self.closest_idx + self.n_waypoints > len(self.waypoints):
			self.look_ahead = self.waypoints[self.closest_idx: ]
		else:
			self.look_ahead = self.waypoints[self.closest_idx: self.closest_idx + self.n_waypoints]
	"""

	def reset(self): 
		x = random.uniform(-1., 1.) # Reset to random point on unit circle
		y = random.choice([-1., 1.])*math.sqrt(1. - x**2) # Reset to random point on unit circle
		theta = self.get_heading([x, y], self.target) # Calculate heading of random point
		yaw = random.uniform(theta - THETA0, theta + THETA0) # Reset to random yaw
		self.pose = np.array([x/MAX_X, y/MAX_Y, yaw]) # Set current position
		self.traj_x = [x]
		self.traj_y = [y]
		self.traj_yaw = [yaw]
		return np.array(self.pose)

	def get_reward(self):
		x_target = self.target[0] # Final goal point in the trajectory
		y_target = self.target[1] # Final goal point in the trajectory
		yaw_target = self.target[2] # Final goal point in the trajectory
		x = self.pose[0]
		y = self.pose[1]
		yaw_car = self.pose[2]
		head_to_target = self.get_heading(self.pose, self.target) # Heading to the target
		"""
		alpha = Difference (Angle made by the target waypoint wrt to x-axis(?),Current pose of the car)
		"""
		# alpha,idx_nxt = self.getAngularSeperationAndIdx()
		alpha = head_to_target - self.pose[2]  # Heading difference for cross track error calculation
		ld = self.get_distance(self.pose, self.target) # Distance to closest waypoint
		crossTrackError = math.sin(alpha) * ld # Calulcation of cross-track error

		return -1*( 0*abs(crossTrackError) + (x - x_target)**2 + abs(y - y_target)**2 + 0*abs (head_to_target - yaw_car)/1.57)
		# reward includes cross track error, along-track error and heading error

	def get_distance(self,x1,x2):
		# Distance between points x1 and x2
		return math.sqrt((x1[0] - x2[0])**2 + (x1[1] - x2[1])**2)

	def get_heading(self, x1,x2):
		# Heading between points x1,x2 with +X axis
		return math.atan2((x2[1] - x1[1]), (x2[0] - x1[0]))		

	def step(self,action):
		# Take step as per policy
		reward = 0
		done = False
		info = {}
		self.action = action
		pos_x = self.pose[0]
		pos_y = self.pose[1]
		pos_theta = self.pose[2]
		self.pose = self.update_state(self.pose, action, 0.005) # 0.005 Modify time discretization

		if ((abs(self.pose[0]) < 1.) and (abs(self.pose[1]) < 1.)):
			# If car is inside MAX_X, MAX_Y grid
			if(abs(self.pose[0]-self.target[0])<THRESHOLD_DISTANCE_2_GOAL and  abs(self.pose[1]-self.target[1])<THRESHOLD_DISTANCE_2_GOAL):
				# If car has reached the final goal
				reward = 15            
				done = True
				print('Goal Reached')
				print("Distance : {:.3f} {:.3f}".format(abs(self.pose[0]-self.target[0])*MAX_X, abs(self.pose[1]-self.target[1])*MAX_Y))
			else:
				# If not reached the goal
				reward = self.get_reward()
				
		else :
			# If car is outside MAX_X, MAX_Y grid
			done = True
			reward = -1.
			print("Outside range")
			print("Distance : {:.3f} {:.3f}".format(abs(self.pose[0]-self.target[0])*MAX_X, abs(self.pose[1]-self.target[1])*MAX_Y))

		return np.array(self.pose), reward, done, info     

	def render(self):
		# Storing tracked trajectory 
		self.traj_x.append(self.pose[0]*MAX_X)
		self.traj_y.append(self.pose[1]*MAX_Y)
		self.traj_yaw.append(self.pose[2])
	  
		plt.cla()
		# for stopping simulation with the esc key.
		plt.gcf().canvas.mpl_connect('key_release_event',
				lambda event: [exit(0) if event.key == 'escape' else None])
		plt.plot(self.traj_x, self.traj_y, "ob", markersize = 2, label="trajectory")
		plt.plot(self.target[0]*MAX_X, self.target[1]*MAX_Y, "xg", label="target")
		# Rendering the car and action taken
		self.plot_car()
		plt.axis("equal")
		plt.grid(True)
		plt.title("Simulation")
		plt.pause(0.0001)
		

	def close(self):
		# For Gym API compatibility
		pass

	def update_state(self, state, a, DT):
		# Update the pose as per Dubin's equations
		throttle = 1
		steer = a[1]

		if steer >= MAX_STEER:
			steer = MAX_STEER
		elif steer <= -MAX_STEER:
			steer = -MAX_STEER

		if throttle > MAX_SPEED:
			throttle = MAX_SPEED
		elif throttle < MIN_SPEED:
			throttle = MIN_SPEED


		state[0] = state[0] + throttle * math.cos(state[2]) * DT
		state[1] = state[1] + throttle * math.sin(state[2]) * DT
		state[2] = state[2] + throttle / WB * math.tan(steer) * DT

		return state

	def plot_car(self, cabcolor="-r", truckcolor="-k"):  # pragma: no cover
		# print("Plotting Car")
		# Scale up the car pose to MAX_X, MAX_Y grid
		x = self.pose[0]*MAX_X #self.pose[0]
		y = self.pose[1]*MAX_Y #self.pose[1]
		yaw = self.pose[2] #self.pose[2]
		steer = self.action[1]*MAX_STEER #self.action[1]

		outline = np.array([[-BACKTOWHEEL, (LENGTH - BACKTOWHEEL), (LENGTH - BACKTOWHEEL), -BACKTOWHEEL, -BACKTOWHEEL],
							[WIDTH / 2, WIDTH / 2, - WIDTH / 2, -WIDTH / 2, WIDTH / 2]])

		fr_wheel = np.array([[WHEEL_LEN, -WHEEL_LEN, -WHEEL_LEN, WHEEL_LEN, WHEEL_LEN],
							 [-WHEEL_WIDTH - TREAD, -WHEEL_WIDTH - TREAD, WHEEL_WIDTH - TREAD, WHEEL_WIDTH - TREAD, -WHEEL_WIDTH - TREAD]])

		rr_wheel = np.copy(fr_wheel)

		fl_wheel = np.copy(fr_wheel)
		fl_wheel[1, :] *= -1
		rl_wheel = np.copy(rr_wheel)
		rl_wheel[1, :] *= -1

		Rot1 = np.array([[math.cos(yaw), math.sin(yaw)],
						 [-math.sin(yaw), math.cos(yaw)]])
		Rot2 = np.array([[math.cos(steer), math.sin(steer)],
						 [-math.sin(steer), math.cos(steer)]])

		fr_wheel = (fr_wheel.T.dot(Rot2)).T
		fl_wheel = (fl_wheel.T.dot(Rot2)).T
		fr_wheel[0, :] += WB
		fl_wheel[0, :] += WB

		fr_wheel = (fr_wheel.T.dot(Rot1)).T
		fl_wheel = (fl_wheel.T.dot(Rot1)).T

		outline = (outline.T.dot(Rot1)).T
		rr_wheel = (rr_wheel.T.dot(Rot1)).T
		rl_wheel = (rl_wheel.T.dot(Rot1)).T

		outline[0, :] += x
		outline[1, :] += y
		fr_wheel[0, :] += x
		fr_wheel[1, :] += y
		rr_wheel[0, :] += x
		rr_wheel[1, :] += y
		fl_wheel[0, :] += x
		fl_wheel[1, :] += y
		rl_wheel[0, :] += x
		rl_wheel[1, :] += y

		plt.plot(np.array(outline[0, :]).flatten(),
				 np.array(outline[1, :]).flatten(), truckcolor)
		plt.plot(np.array(fr_wheel[0, :]).flatten(),
				 np.array(fr_wheel[1, :]).flatten(), truckcolor)
		plt.plot(np.array(rr_wheel[0, :]).flatten(),
				 np.array(rr_wheel[1, :]).flatten(), truckcolor)
		plt.plot(np.array(fl_wheel[0, :]).flatten(),
				 np.array(fl_wheel[1, :]).flatten(), truckcolor)
		plt.plot(np.array(rl_wheel[0, :]).flatten(),
				 np.array(rl_wheel[1, :]).flatten(), truckcolor)
		plt.plot(x, y, "*") 

def get_value_lyapunov(x1,x2,x3):
  value=0

  index_1=0
  index_2=0
  index_3=0

  for i in range(dim1):
    if x1>x_1[i]:
          index_1=i

  for i in range(dim2):
    if x2>x_2[i]:
        index_3=i

  for i in range(dim3):
    if x3>x_3[i]:
          index_3=i

  value = tf.keras.backend.eval(V_1[index_1,index_2,index_3])


  return value

def main():

	### Declare variables for environment
	env =  DubinGym([1., 0., -1.57])
	## Model Training
	agent = SAC(env.observation_space.shape[0], env.action_space, args)
	# Memory
	memory = ReplayMemory(args.replay_size, args.seed)
	#Tensorboard
	writer = SummaryWriter('runs/{}_SAC_{}_{}_{}'.format(datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S"), 'DeepracerGym',
														 args.policy, "autotune" if args.automatic_entropy_tuning else ""))

	# Training parameters
	total_numsteps = 0

	updates = 0
	num_goal_reached = 0
	global rewards_list
	rewards_list = []
	episodes=0

	for i_episode in itertools.count(1):
		episodes+=1
		# Training Loop
		# print("New episode")
		episode_reward = 0
		episode_steps = 0
		done = False
		state = env.reset()
		episode_rewards=[]
		
		while not done:
			
            
			if total_numsteps>100000:
				env.render() # Rendering toggle

			start_time = time.time()
			if args.start_steps > total_numsteps:
				action = env.action_space.sample()  # Sample random action
			else:
				action = agent.select_action(state)  # Sample action from policy

			next_state, reward, done, _ = env.step(action) # Step
			if (reward > 9) and (episode_steps > 1): #Count the number of times the goal is reached
				num_goal_reached += 1 

			episode_steps += 1
			total_numsteps += 1
			episode_reward += reward
			episode_rewards.append(episode_reward)		
			if episode_steps > args.max_episode_length:
				done = True

			# Ignore the "done" signal if it comes from hitting the time horizon.
			# (https://github.com/openai/spinningup/blob/master/spinup/algos/sac/sac.py)
			mask = 1 if episode_steps == args.max_episode_length else float(not done)
			# mask = float(not done)
			memory.push(state, action, reward, next_state, mask) # Append transition to memory

			state = next_state
			# print(done)

		# if i_episode % UPDATE_EVERY == 0: 
		if len(memory) > args.batch_size:
			# Number of updates per step in environment
			for i in range(args.updates_per_step*args.max_episode_length):
				# Update parameters of all the networks
				critic_1_loss, critic_2_loss, policy_loss, ent_loss, alpha = agent.update_parameters(memory, args.batch_size, updates)

				writer.add_scalar('loss/critic_1', critic_1_loss, updates)
				writer.add_scalar('loss/critic_2', critic_2_loss, updates)
				writer.add_scalar('loss/policy', policy_loss, updates)
				writer.add_scalar('loss/entropy_loss', ent_loss, updates)
				writer.add_scalar('entropy_temprature/alpha', alpha, updates)
				updates += 1

		if total_numsteps > args.num_steps:
			break

		if episodes>100:
			break

		if (episode_steps > 1):
			writer.add_scalar('reward/train', episode_reward, i_episode)
			writer.add_scalar('reward/episode_length',episode_steps, i_episode)
			writer.add_scalar('reward/num_goal_reached',num_goal_reached, i_episode)

		print("Episode: {}, total numsteps: {}, episode steps: {}, reward: {}".format(i_episode, total_numsteps, episode_steps, round(episode_reward, 2)))
		print("Number of Goals Reached: ",num_goal_reached)
		rewards_list.append(episode_reward)
		sigma.append(np.std(episode_rewards))
		
		


	print('----------------------Training Ending----------------------')
	# env.stop_car()

	agent.save_model("random_initial", suffix = "2") # Rename it as per training scenario
	return True

	## Environment Quick Test
	# max_steps = int(1e6)
	# state = env.reset()
	# env.render()
	# for ep in range(5):
	# 	state = env.reset()
	# 	env.render()



 
	# 	for i in range(max_steps):
	# 		action = [1.0, 0.]
	# 		n_state,reward,done,info = env.step(action)
	# 		env.render()
	# 		if done:
	# 			state = env.reset()
	# 			done = False                   
	# 			break

if __name__ == '__main__':
	for i in range (50):
		main()
		mu1=np.array(rewards_list)
		filename='reward_SAC'+str(i)+'.txt'
		np.savetxt("/home/al55293/RL-with-Lyapunov-functions/dubin_model_gymenv/rewards_data/rewards_SAC_2nd/"+filename,mu1)
		

# Define function to plot rewards over time
'''t=np.arange(len(rewards_list))
mu1=np.array(rewards_list)
sigma1=np.array(sigma)

np.savetxt("reward_CLVF.txt",mu1)
np.savetxt("std_CLVF.txt",sigma1)

fig, ax = plt.subplots(1)
ax.plot(t, mu1, lw=2, label='CLF gamma=0.8', color='blue')
#ax.plot(t, mu2, lw=2, label='mean population 2', color='yellow')
ax.fill_between(t, mu1+sigma1, mu1-sigma1, facecolor='blue', alpha=0.5)
#ax.fill_between(t, mu2+sigma2, mu2-sigma2, facecolor='yellow', alpha=0.5)
ax.set_title('Dubins Car reward for different RL algorithms')
ax.legend(loc='lower right')
ax.set_xlabel('num episodes')
ax.set_ylabel('average reward')
ax.grid()
plt.show()
'''


	
    

