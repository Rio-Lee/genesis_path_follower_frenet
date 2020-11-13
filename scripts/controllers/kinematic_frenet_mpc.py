# This is a modified version of kinematic_mpc.py from genesis_path_follower GitHub repo.

import time
import casadi
import numpy as np
from controller import Controller

class KinMPCPathFollower(Controller):
	##
	def __init__(self, 
		         N          = 10,     # timesteps in MPC Horizon
		         DT_MODEL	= 0.2,    # discretization time between timesteps (s)
				 DT	= 0.2,    
		         L_F        = 1.5213, # distance from CoG to front axle (m)
		         L_R        = 1.4987, # distance from CoG to rear axle (m)
				 V_SET		= 45./2.237,	# velocity set by a driver (m/s)
				 AX_MAX     =  5.0,		
		         AX_MIN     = -10.0,   # min/max acceleration constraint (m/s^2) 
				 AY_MAX     =  4.0,		
				 AY_MIN     = -4.0,  	
		         DF_MAX     =  30*np.pi/180,
		         DF_MIN     = -30*np.pi/180,   # min/max front steer angle constraint (rad)
		         AX_DOT_MAX  =  3.,
		         AX_DOT_MIN  = -3.,   # min/max jerk constraint (m/s^3)
				 AY_DOT_MAX  =  5.,
		         AY_DOT_MIN  = -5.,   # min/max jerk constraint (m/s^3)
		         DF_DOT_MAX =  30*np.pi/180,
		         DF_DOT_MIN = -30*np.pi/180,   # min/max front steer angle rate constraint (rad/s)
		         EY_MAX		=  0.8,
				 EY_MIN		= -0.8,
				 EPSI_MAX	=  10*np.pi/180,
				 EPSI_MIN	= -10*np.pi/180,
				 Q = [0., 100., 500., 1., 0.],  # s, ey, epsi, v, ay
				 R = [.01, .001]):  # ax, df

		for key in list(locals()):
			if key == 'self':
				pass
			elif key == 'Q':
				self.Q = casadi.diag(Q)
			elif key == 'R':
				self.R = casadi.diag(R)
			else:
				setattr(self, '%s' % key, locals()[key])

		self.opti = casadi.Opti()

		''' 
		(1) Parameters
		'''		
		##
		self.u_prev  = self.opti.parameter(2) # previous input: [u_{acc, -1}, u_{df, -1}]
		self.z_curr  = self.opti.parameter(5) # current state:  [s0, ey_0, epsi_0, v_0, Not Used]

		# Reference trajectory we would like to follow.
		# First index corresponds to our desired state at timestep k+1:
		#   i.e. z_ref[0,:] = z_{desired, 1}.
		# Second index selects the state element from [x_k, y_k, psi_k, v_k].
		self.z_ref = self.opti.parameter(self.N, 4)
		self.z_ref2 = self.opti.parameter(1, 5) # [Not Used, Not Used, Not Used, v_ref, Not Used]

		## Reference curvature we would like to follow.
		self.x_ref   = self.z_ref[:,0]
		self.y_ref   = self.z_ref[:,1]
		self.psi_ref = self.z_ref[:,2]
		self.v_ref   = self.z_ref[:,3]

		self.curv_ref = self.opti.parameter(self.N)

		'''
		(2) Decision Variables
		'''
		## First index is the timestep k, i.e. self.z_dv[0,:] is z_0.		
		## It has self.N+1 timesteps since we go from z_0, ..., z_self.N.
		## Second index is the state element, as detailed below.
		self.z_dv = self.opti.variable(self.N+1, 5) # s, ey, epsi, v, ay
	
		self.s_dv   = self.z_dv[:, 0]  
		self.ey_dv   = self.z_dv[:, 1]  
		self.epsi_dv = self.z_dv[:, 2]  
		self.v_dv   = self.z_dv[:, 3]  
		self.ay_dv   = self.z_dv[:, 4]
		
		## Control inputs used to achieve self.z_dv according to dynamics.
		## First index is the timestep k, i.e. self.u_dv[0,:] is u_0.
		## Second index is the input element as detailed below.
		self.u_dv = self.opti.variable(self.N, 2)

		self.acc_dv = self.u_dv[:,0]
		self.df_dv  = self.u_dv[:,1]

		# Slack variables used to relax input rate constraints.
		# Matches self.u_dv in structure but timesteps range from -1, ..., N-1.

		self.sl_dv  = self.opti.variable(self.N , 1)
		
		self.sl_ay_dv = self.sl_dv[:,0]
		
		'''
		(3) Problem Setup: Constraints, Cost, Initial Solve
		'''

		self._add_constraints()

		self._add_cost()	

		self._update_initial_condition(0., 0., 0., 1., 0.)

		self._update_reference([self.DT * (x+1) for x in range(self.N)],
			                  self.N*[0.], 
			                  self.N*[0.], 
			                  self.N*[1.])
		
		self._update_reference2(self.N*[0.], [0., 0., 0., 20., 0.])
		
		self._update_previous_input(0., 0.)
		
		# Ipopt with custom options: https://web.casadi.org/docs/ -> see sec 9.1 on Opti stack.
		p_opts = {'expand': True}
		s_opts = {'max_cpu_time': 0.1, 'print_level': 0} 
		self.opti.solver('ipopt', p_opts, s_opts)

		sol = self.solve()

	def _add_constraints(self):
		## State Bound Constraints
		self.opti.subject_to( self.opti.bounded(self.EY_MIN, self.ey_dv, self.EY_MAX) )
		self.opti.subject_to( self.opti.bounded(self.EPSI_MIN, self.epsi_dv, self.EPSI_MAX) )
		for i in range(self.N):
			self.opti.subject_to( self.opti.bounded(self.AY_MIN - self.sl_ay_dv[i], self.ay_dv, self.AY_MAX + self.sl_ay_dv[i]) )		

		## Initial State Constraint
		self.opti.subject_to( self.s_dv[0]   == self.z_curr[0] )   
		self.opti.subject_to( self.ey_dv[0]   == self.z_curr[1] )  
		self.opti.subject_to( self.epsi_dv[0] == self.z_curr[2] )  
		self.opti.subject_to( self.v_dv[0]   == self.z_curr[3] )   
		
		## State Dynamics Constraints
		for i in range(self.N):
			beta = casadi.atan( self.L_R / (self.L_F + self.L_R) * casadi.tan(self.df_dv[i]) )
			dyawdt = self.v_dv[i] / self.L_R * casadi.sin(beta)
			dsdt = self.v_dv[i] * casadi.cos(self.epsi_dv[i]+beta) / (1 - self.ey_dv[i] * self.curv_ref[i] )   
			

			self.opti.subject_to( self.s_dv[i+1] == self.s_dv[i] + self.DT_MODEL * (dsdt) )  
			self.opti.subject_to( self.ey_dv[i+1] == self.ey_dv[i] + self.DT_MODEL * (self.v_dv[i]) * casadi.sin(self.epsi_dv[i] + beta) ) 
			self.opti.subject_to( self.epsi_dv[i+1] == self.epsi_dv[i] + self.DT_MODEL * (dyawdt - dsdt * self.curv_ref[i]) )
			self.opti.subject_to( self.v_dv[i+1] == self.v_dv[i] + self.DT_MODEL * (self.acc_dv[i]) )
			self.opti.subject_to( self.ay_dv[i] == self.v_dv[i] * dyawdt)
            
		## Input Bound Constraints
		self.opti.subject_to( self.opti.bounded(self.AX_MIN,  self.acc_dv, self.AX_MAX) )
		self.opti.subject_to( self.opti.bounded(self.DF_MIN, self.df_dv,  self.DF_MAX) )

		# Input Rate Bound Constraints
		self.opti.subject_to( self.opti.bounded( self.AX_DOT_MIN, 
			                                     self.acc_dv[0] - self.u_prev[0],
			                                     self.AX_DOT_MAX) )

		self.opti.subject_to( self.opti.bounded( self.DF_DOT_MIN, 
			                                     self.df_dv[0] - self.u_prev[1],
			                                     self.DF_DOT_MAX) )

		for i in range(self.N - 1):
			self.opti.subject_to( self.opti.bounded( self.AX_DOT_MIN, 
				                                     self.acc_dv[i+1] - self.acc_dv[i],
				                                     self.AX_DOT_MAX) )
			self.opti.subject_to( self.opti.bounded( self.DF_DOT_MIN, 
				                                     self.df_dv[i+1]  - self.df_dv[i],
				                                     self.DF_DOT_MAX) )
		# Other Constraints

		self.opti.subject_to( self.opti.bounded(0, self.sl_ay_dv, 1) )
		# e.g. things like collision avoidance or lateral acceleration bounds could go here.
	
	## Cost function
	def _add_cost(self):
		def _quad_form(z, Q):
			return casadi.mtimes(z, casadi.mtimes(Q, z.T))	
		
		cost = 0
		for i in range(self.N):
			cost += _quad_form(self.z_dv[i, :]-self.z_ref2, self.Q)

		for i in range(self.N - 1):
			cost += _quad_form(self.u_dv[i+1, :] - self.u_dv[i,:], self.R)
		
		cost += casadi.sum1(self.sl_ay_dv)
		self.opti.minimize( cost )

	def solve(self):
		st = time.time()
		try:
			sol = self.opti.solve()
			# Optimal solution.
			u_mpc  = sol.value(self.u_dv)
			z_mpc  = sol.value(self.z_dv)
			sl_mpc = sol.value(self.sl_dv)
			z_ref  = sol.value(self.z_ref)
			is_opt = True
		except:
			# Suboptimal solution (e.g. timed out).
			u_mpc  = self.opti.debug.value(self.u_dv)
			z_mpc  = self.opti.debug.value(self.z_dv)
			sl_mpc = self.opti.debug.value(self.sl_dv)
			z_ref  = self.opti.debug.value(self.z_ref)
			is_opt = False

		solve_time = time.time() - st
		
		sol_dict = {}
		sol_dict['u_control']  = u_mpc[0,:]  # control input to apply based on solution
		sol_dict['optimal']    = is_opt      # whether the solution is optimal or not
		sol_dict['solve_time'] = solve_time  # how long the solver took in seconds
		sol_dict['u_mpc']      = u_mpc       # solution inputs (N by 2, see self.u_dv above) 
		sol_dict['z_mpc']      = z_mpc       # solution states (N+1 by 4, see self.z_dv above)
		sol_dict['sl_mpc']     = sl_mpc      # solution slack vars (N by 2, see self.sl_dv above)
		sol_dict['z_ref']      = z_ref       # state reference (N by 4, see self.z_ref above)

		return sol_dict

	def update(self, update_dict):
		# TODO: 'psi0' should be replaced by 'ay0' later.
		self._update_initial_condition( *[update_dict[key] for key in ['s', 'e_y', 'e_psi', 'v0', 'psi0']] )	
		self._update_reference( *[update_dict[key] for key in ['x_ref', 'y_ref', 'psi_ref', 'v_ref']] )
		
		# Calculate the maximum from the upcoming curvatures.
		curvature_max = max(abs(update_dict['curv_ref']))
		v_target = np.sqrt(self.AY_MAX/abs(curvature_max))
		v_target = min(self.V_SET, v_target)
		self._update_reference2( update_dict['curv_ref'], [0, 0, 0, v_target, 0] )

		self._update_previous_input( *[update_dict[key] for key in ['acc_prev', 'df_prev']] )

		if 'warm_start' in update_dict.keys():
			# Warm Start used if provided.  Else I believe the problem is solved from scratch with initial values of 0.
			self.opti.set_initial(self.z_dv,  update_dict['warm_start']['z_ws'])
			self.opti.set_initial(self.u_dv,  update_dict['warm_start']['u_ws'])
			self.opti.set_initial(self.sl_dv, update_dict['warm_start']['sl_ws'])

	##
	def _update_initial_condition(self, s0, ey0, epsi0, vel0, ay0):
		self.opti.set_value(self.z_curr, [s0, ey0, epsi0, vel0, ay0])

	def _update_reference(self, x_ref, y_ref, psi_ref, v_ref):
		self.opti.set_value(self.x_ref,   x_ref)
		self.opti.set_value(self.y_ref,   y_ref)
		self.opti.set_value(self.psi_ref, psi_ref)
		self.opti.set_value(self.v_ref,   v_ref)

	##
	def _update_reference2(self, curv_ref, z_ref2):
		self.opti.set_value(self.curv_ref, curv_ref)
		self.opti.set_value(self.z_ref2, z_ref2)

	def _update_previous_input(self, acc_prev, df_prev):
		self.opti.set_value(self.u_prev, [acc_prev, df_prev])

if __name__ == '__main__':
	kmpc = KinMPCPathFollower()
	sol_dict = kmpc.solve()
	
	for key in sol_dict:
		print(key, sol_dict[key])
