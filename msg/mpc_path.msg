Header header
string solve_status # e.g. optimal, infeasible, etc.
float64 solve_time  # time used to solve the optimization problem in seconds
float64[] xs        # MPC solution for x coordinate (m)
float64[] ys        # MPC solution for y coordinate (m)
float64[] vs        # MPC solution for speed (m/s)
float64[] psis      # MPC solution for yaw angle (rad)
float64[] xr        # MPC reference for ""
float64[] yr        # MPC reference for ""
float64[] vr        # MPC reference for ""
float64[] psir      # MPC reference for ""
float64[] df        # MPC solution for front steering angle (rad)
float64[] acc       # MPC solution for acceleration (m/s^2)
float64 s
float64 e_y
float64 e_psi
float64[] ay_mdl
float64 v_ref
float64[] xy_waypoint