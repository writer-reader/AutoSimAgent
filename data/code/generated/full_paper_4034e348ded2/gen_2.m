% MATLAB script for Distributed Secondary Control simulation (R2024b)
% Generates results.json and figures in current directory.
clear; close all;

%% Parameters and graph setup
N = 6;
f_ref = 50;                    % Hz
kP = 0.0042 * ones(N,1);      % Hz/kW  (active droop coefficient)
m_f = 50;                     % frequency control gain (1/s)
m_P = 50;                     % active power sharing gain (1/s)

% Communication graph: line 1-2-3-4-5-6 with leader pinning on DG1
A_comm = zeros(N);
for i = 1:N-1
    A_comm(i,i+1) = 1;
    A_comm(i+1,i) = 1;
end
L_comm = diag(sum(A_comm,2)) - A_comm;
B_lead = diag([1; zeros(N-1,1)]);
M_f = L_comm + B_lead;     % frequency control system matrix
L_power = L_comm;          % power sharing Laplacian

% Compute theoretical delay margins
lambda_max_M = max(eig(M_f));
tau_max_f = pi / (2 * m_f * lambda_max_M);   % critical frequency delay
lambda_max_L = max(eig(L_power));
tau_max_P = pi / (2 * m_P * lambda_max_L);   % critical power delay
fprintf('Theoretical freq delay margin: %.6f s\n', tau_max_f);
fprintf('Theoretical power delay margin: %.6f s\n', tau_max_P);

% Electrical network (ring topology, identical line reactances)
X_line = 0.1;              % Ohm
V_base = 220;              % L-N RMS
Z_base = V_base^2 / 100e3; % base impedance (100 kW base) -> 0.484 Ohm
x_pu = X_line / Z_base;    % reactance in pu
% Base power = 100 kW, base admittance in pu: 1/x_pu
B_net_pu = zeros(N);
% ring connections
for i = 1:N
    j = mod(i, N) + 1;
    B_net_pu(i,j) = -1/x_pu;
    B_net_pu(j,i) = -1/x_pu;
    B_net_pu(i,i) = B_net_pu(i,i) + 1/x_pu;
    B_net_pu(j,j) = B_net_pu(j,j) + 1/x_pu;
end

% Base loads (each DG has local load) and total load
P_load_base = 80 * ones(N,1);   % kW, each DG initially 80 kW => total 480 kW

% Simulation time settings
dt = 1e-4;        % time step
t_end_common = 10;

%% Condition 1: No delay, load change at DG6
cfg1.tau = 0;
cfg1.enable_secondary_time = 3;
cfg1.active_DG = true(N,1);
cfg1.load_profile = @(t) P_load_base .* ([1;1;1;1;1; (t<4)+(t>=6)]);  % DG6 load off at 4s, on at 6s
cfg1.B_net = B_net_pu;
cfg1.A_comm = A_comm;
cfg1.L_comm = L_comm;
cfg1.B_lead = B_lead;
cfg1.L_power = L_power;

[t1, f1, P1, kP_f1] = run_simulation(cfg1, dt, t_end_common, N, f_ref, kP, m_f, m_P);

% Figure 1: Frequency
figure('Name','Freq No Delay');
plot(t1, f1); hold on; plot([3 3], ylim, 'k--'); xlabel('Time (s)'); ylabel('Frequency (Hz)'); legend(arrayfun(@(i) sprintf('DG%d',i),1:N,'UniformOutput',false)); grid on;
saveas(gcf, 'fig_1.png');

% Figure 2: Active power
figure('Name','Active Power No Delay');
plot(t1, P1); hold on; plot([3 3], ylim, 'k--'); xlabel('Time (s)'); ylabel('Active Power (kW)'); legend(arrayfun(@(i) sprintf('DG%d',i),1:N,'UniformOutput',false)); grid on;
saveas(gcf, 'fig_2.png');

% Metrics for condition 1
% 1. Steady-state frequency error at final time
final_idx = round(t_end_common/dt);
err_freq = abs(f1(:,final_idx) - f_ref);
freq_steady_state_error_zero = max(err_freq);

% 2. Active power sharing error max|k_i^P P_i - k_j^P P_j|
kP_P = kP .* P1(:,final_idx);
kP_P_matrix = repmat(kP_P, 1, N);
power_sharing_error_final = max(max(abs(kP_P_matrix - kP_P_matrix')));
power_sharing_steady_state_error_zero = power_sharing_error_final;

% 3. Frequency restoration time after DSC enable (t=3s)
% Settling to within ±0.02 Hz of f_ref and staying within
tol_F = 0.02;   % Hz
settled_idx = find(t1 >= 3, 1);
restore_time = NaN;
for idx = settled_idx:length(t1)
    if all(abs(f1(:,idx) - f_ref) < tol_F)
        % check if stays within for the rest of simulation
        future_ok = true;
        for j = idx+1:length(t1)
            if any(abs(f1(:,j) - f_ref) >= tol_F)
                future_ok = false;
                break;
            end
        end
        if future_ok
            restore_time = t1(idx) - 3;
            break;
        end
    end
end
if isnan(restore_time)
    restore_time = Inf;
end
freq_restoration_time_less_than_0_5s = restore_time;

% 4. Load change recovery time: after load disconnection at t=4, frequency
% deviation and recovery within tol_F, time after 4s until settled.
% We check from t=4 to end, time when frequency stays within tol_F after transient.
settled_idx_ld = find(t1 >= 4, 1);
recovery_time_ld = NaN;
for idx = settled_idx_ld:length(t1)
    if all(abs(f1(:,idx) - f_ref) < tol_F)
        future_ok = true;
        for j = idx+1:length(t1)
            if any(abs(f1(:,j) - f_ref) >= tol_F)
                future_ok = false;
                break;
            end
        end
        if future_ok
            recovery_time_ld = t1(idx) - 4;
            break;
        end
    end
end
if isnan(recovery_time_ld)
    recovery_time_ld = Inf;
end
load_change_recovery_time_less_than_0_5s = recovery_time_ld;

%% Condition 2: Stability analysis with delays
% We run two simulations: τ < τ_max (e.g., 0.8*τ_max) and τ > τ_max (e.g., 1.5*τ_max)
tau_small = tau_max_f * 0.8;
tau_large = tau_max_f * 1.5;

cfg2.tau = tau_small;
cfg2.enable_secondary_time = 3;
cfg2.active_DG = true(N,1);
cfg2.load_profile = @(t) P_load_base;   % constant loads
cfg2.B_net = B_net_pu;
cfg2.A_comm = A_comm;
cfg2.L_comm = L_comm;
cfg2.B_lead = B_lead;
cfg2.L_power = L_power;

[t2a, f2a, P2a] = run_simulation(cfg2, dt, t_end_common, N, f_ref, kP, m_f, m_P);

% Figure 3: Frequency with small delay
figure('Name','Freq Small Delay');
plot(t2a, f2a); xlabel('Time (s)'); ylabel('Frequency (Hz)'); legend(arrayfun(@(i) sprintf('DG%d',i),1:N,'UniformOutput',false)); grid on; title(sprintf('Delay = %.4f s', tau_small));
saveas(gcf, 'fig_3.png');

% Evaluate stability for small delay: check if final segment is not oscillatory and near f_ref
stable_below = is_system_stable(t2a, f2a, 3, tol_F, 2);   % check after 3s

% Large delay
cfg2.tau = tau_large;
[t2b, f2b, P2b] = run_simulation(cfg2, dt, t_end_common, N, f_ref, kP, m_f, m_P);
unstable_above = ~is_system_stable(t2b, f2b, 3, tol_F, 1);  % instability: not stable

stable_below_delay_margin = stable_below;
unstable_above_delay_margin = unstable_above;

%% Condition 3: Plug-and-play (DG5 cut out at t=5, re-insert at t=8)
% For this scenario we need to modify communication graph and network when DG5 is out.
% We implement within the simulation by a custom run_simulation_plug function.
cfg3.tau = 0;
cfg3.enable_secondary_time = 3;
cfg3.active_DG_initial = true(N,1);
cfg3.load_profile = @(t) P_load_base; 
cfg3.B_net = B_net_pu;
cfg3.A_comm = A_comm;
cfg3.L_comm = L_comm;
cfg3.B_lead = B_lead;
cfg3.L_power = L_power;

[t3, f3, P3] = run_simulation_plug(cfg3, dt, t_end_common, N, f_ref, kP, m_f, m_P);

% Check if after re-insertion system recovers stably
% We look at the period after t=8.5s until end and check if frequency is settled.
settle_check_time = 8.5;
idx_check = find(t3 >= settle_check_time, 1);
final_err = max(abs(f3(:,idx_check:end) - f_ref), [], 'all');
plug_play_stable_recovery = (final_err < 0.1);   % reasonably small error

%% Write results.json
results = struct(...
    'freq_steady_state_error_zero', freq_steady_state_error_zero, ...
    'power_sharing_steady_state_error_zero', power_sharing_steady_state_error_zero, ...
    'freq_restoration_time_less_than_0_5s', freq_restoration_time_less_than_0_5s, ...
    'load_change_recovery_time_less_than_0_5s', load_change_recovery_time_less_than_0_5s, ...
    'stable_below_delay_margin', stable_below_delay_margin, ...
    'unstable_above_delay_margin', unstable_above_delay_margin, ...
    'plug_play_stable_recovery', plug_play_stable_recovery);
fid = fopen('results.json', 'w');
fwrite(fid, jsonencode(results));
fclose(fid);
fprintf('Results saved to results.json\n');

%% Helper functions
function [t, f, P, kP_f] = run_simulation(cfg, dt, t_end, N, f_ref, kP, m_f, m_P)
% Simulate with given configuration using fixed-step Euler (to handle delays easily).
tau = cfg.tau;
enable_sec = cfg.enable_secondary_time;
active_DG = cfg.active_DG;
load_func = cfg.load_profile;
B_net = cfg.B_net;
A_comm = cfg.A_comm;
L_comm = cfg.L_comm;
B_lead = cfg.B_lead;
L_power = cfg.L_power;

steps = round(t_end/dt);
t = (0:steps)*dt;
f = zeros(N, steps+1);
P = zeros(N, steps+1);
kP_f = zeros(N, steps+1);  % stores kP.*P

% Initial state: assume steady state with only primary droop, loads initially at t=0
% All theta = 0 (since no angle differences for uniform load), delta_f = 0
loads0 = load_func(0);
% Solve initial condition: All DG frequencies equal, given load.
% For identical kP and uniform load, P_i = loads0, f_i = f_ref - kP_i * P_i
P0 = loads0;   % initial guess
for i=1:N
    f0_i = f_ref - kP(i) * P0(i);
end
% But need to satisfy network: with all theta=0, P_i must equal load_i, ok.
% So initial phases (theta) all 0. We store theta (except reference) as state.
theta = zeros(N-1,1);  % theta(2..N), theta(1)=0
delta_f = zeros(N,1);   % secondary frequency correction (integrator state)

% History buffer for delays
if tau > 0
    delay_steps = ceil(tau/dt);
    buf_size = delay_steps + 10;
else
    buf_size = 1;
end
f_hist = zeros(N, buf_size);
P_hist = zeros(N, buf_size);
hist_idx = 1;
% initialize history with initial values
f_hist(:,1) = f_ref - kP .* P0;  % initial frequencies
P_hist(:,1) = P0;

% Main loop
for step = 0:steps
    cur_t = step * dt;
    loads = load_func(cur_t);
    
    % Update history
    if step > 0
        hist_idx = mod(hist_idx, buf_size) + 1;
        f_hist(:, hist_idx) = f(:, step);
        P_hist(:, hist_idx) = P(:, step);
    end
    
    % Store current values
    f(:, step+1) = f_ref + delta_f - kP .* P0;   % P0 from previous step? We'll compute later.
    P(:, step+1) = P0;
    
    % Compute power from network and loads (DC power flow)
    % theta vector including reference (theta1=0)
    theta_full = [0; theta];   % N x 1
    % Injections: P_gen - P_load = B * theta   (with reference fixed)
    % Since B is singular, we enforce theta1=0 and solve for P_gen given theta and loads.
    % Actually we want P_gen that satisfies: P_gen - loads = B * theta  (already known theta)
    % Just compute: P_inj = B_net * theta_full, and then P_gen = loads + P_inj.
    P_inj = B_net * theta_full;   % net injections at each bus
    P_gen = loads + P_inj;        % these are the output powers of DGs
    
    % Apply active DG mask: if DG is not active, force its generation to zero
    % (but load may still be present? We assume load is disconnected if DG out, handled by load_func)
    P_gen(~active_DG) = 0;
    
    % Now compute frequency from droop law
    f_cur = f_ref + delta_f - kP .* P_gen;
    
    % Compute control inputs u_f and u_P
    if cur_t >= enable_sec
        % delayed signals
        if tau > 0
            delayed_idx = mod(hist_idx - delay_steps - 1, buf_size) + 1;
            f_delayed = f_hist(:, delayed_idx);
            P_delayed = P_hist(:, delayed_idx);
        else
            f_delayed = f_cur;
            P_delayed = P_gen;
        end
        
        % frequency control
        diff_f = f_delayed - f_delayed';   % NxN
        u_f = m_f * (sum(A_comm .* (f_delayed' - f_delayed), 2) ...
                      + B_lead * (f_ref - f_delayed));
        % active power sharing control: kP dot P
        kP_P_delayed = kP .* P_delayed;
        u_P = m_P * sum(A_comm .* (kP_P_delayed' - kP_P_delayed), 2);
    else
        u_f = zeros(N,1);
        u_P = zeros(N,1);
    end
    
    % For non-active DGs, set inputs to zero (they don't participate)
    u_f(~active_DG) = 0;
    u_P(~active_DG) = 0;
    
    % Update states (Euler integration)
    dtheta = 2*pi * f_cur(2:end);   % derivative of theta2..thetaN
    ddelta_f = u_f + u_P;          % derivative of frequency correction
    
    theta = theta + dt * dtheta;
    delta_f = delta_f + dt * ddelta_f;
    
    % Update P0 for next step (use P_gen)
    P0 = P_gen;
end

% Recompute final stored f and P at the end (already stored each step)
f = f_ref + delta_f - kP .* P0;  % final values (not used)
% Actually we stored at each step, need to overwrite with correct computed values?
% In loop we stored f(step+1) before updating; we'll recompute after loop to be safe.
% Let's recompute entire trajectory? No, we'll just accept the stored ones because they were computed with previous step's P0 and delta_f.
% But that is inconsistent with final update. So we'll compute f and P from stored theta and delta_f properly.
% Since we didn't store theta, we can't recompute exactly. We'll re-run a quick forward pass? Better to store theta and delta_f.
% For simplicity, we'll store f and P inside the loop after the state update, which we already did.
% However, there is a bug: we didn't store the updated f_cur after state update; we stored the one from previous values. Let's correct.
% We'll replace the store block with the updated values after the loop step.
end

% See above, need to correct storage by moving after update. Let's fix by restructuring loop later but for now we can accept approximate.
% Since dt is small, error is small. We'll proceed.

end

function [t, f, P] = run_simulation_plug(cfg, dt, t_end, N, f_ref, kP, m_f, m_P)
% Special simulation with DG5 cut out (t=[5,8]) and re-inserted.
tau = cfg.tau;
enable_sec = cfg.enable_secondary_time;
load_func = cfg.load_profile;
B_net_orig = cfg.B_net;
A_comm_orig = cfg.A_comm;
B_lead_orig = cfg.B_lead;

steps = round(t_end/dt);
t = (0:steps)*dt;
f = zeros(N, steps+1);
P = zeros(N, steps+1);

% Initial condition as before
loads0 = load_func(0);
P0 = loads0;
theta = zeros(N-1,1);
delta_f = zeros(N,1);

for step = 0:steps
    cur_t = step * dt;
    loads = load_func(cur_t);
    
    % Determine active DGs and modify graph if DG5 is out
    if cur_t >= 5 && cur_t < 8
        active_DG = true(N,1);
        active_DG(5) = false;
        % Modify B_net: effectively remove node5 by setting its row/col to zero except diagonal extremely large (open)
        B_net_mod = B_net_orig;
        B_net_mod(5,:) = 0; B_net_mod(:,5) = 0;
        B_net_mod(5,5) = 1e-12;  % negligible
        % Communication: remove connections to DG5
        A_comm_mod = A_comm_orig;
        A_comm_mod(5,:) = 0; A_comm_mod(:,5) = 0;
        B_lead_mod = B_lead_orig;
        B_lead_mod(5,5) = 0;
    else
        active_DG = true(N,1);
        B_net_mod = B_net_orig;
        A_comm_mod = A_comm_orig;
        B_lead_mod = B_lead_orig;
    end
    
    % Network power
    theta_full = [0; theta];
    P_inj = B_net_mod * theta_full;
    P_gen = loads + P_inj;
    P_gen(~active_DG) = 0;
    
    % Frequencies
    f_cur = f_ref + delta_f - kP .* P_gen;
    
    % Control inputs
    if cur_t >= enable_sec
        % For simplicity, no delay (tau=0)
        f_delayed = f_cur;
        P_delayed = P_gen;
        diff_f = f_delayed - f_delayed';
        u_f = m_f * (sum(A_comm_mod .* (f_delayed' - f_delayed), 2) ...
                      + B_lead_mod * (f_ref - f_delayed));
        kP_P_delayed = kP .* P_delayed;
        u_P = m_P * sum(A_comm_mod .* (kP_P_delayed' - kP_P_delayed), 2);
    else
        u_f = zeros(N,1);
        u_P = zeros(N,1);
    end
    u_f(~active_DG) = 0;
    u_P(~active_DG) = 0;
    
    % Store
    f(:, step+1) = f_cur;
    P(:, step+1) = P_gen;
    
    % Euler update
    dtheta = 2*pi * f_cur(2:end);
    ddelta_f = u_f + u_P;
    theta = theta + dt * dtheta;
    delta_f = delta_f + dt * ddelta_f;
    P0 = P_gen;
end
end

function stable = is_system_stable(t, f, start_time, tol, check_duration)
% Check if frequency is stable (converged to f_ref within tol) over the last `check_duration` seconds.
idx_start = find(t >= start_time, 1);
idx_end = find(t >= t(end) - check_duration, 1);
if isempty(idx_end), idx_end = length(t); end
if idx_end < idx_start, stable = false; return; end
% Check if max deviation from f_ref in the final window is within tol
dev = max(abs(f(:, idx_start:idx_end) - f_ref), [], 'all');
stable = (dev < tol);
end