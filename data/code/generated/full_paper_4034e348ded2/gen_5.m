% Script: microgrid_dsc_simulation.m
clear; close all;

%% Parameters
N = 6;                      % Number of DGs
f_ref = 50;                 % Hz
kP = 0.0042 * ones(N,1);    % Hz/kW, droop coefficient

% Communication network (chain 1-2-3-4-5-6)
A_comm = zeros(N);
for i = 1:N-1
    A_comm(i,i+1) = 1;
    A_comm(i+1,i) = 1;
end
L_comm = diag(sum(A_comm,2)) - A_comm;
% Leader: only DG1 has direct reference access
B_lead = zeros(N); B_lead(1,1) = 1;
M_f = L_comm + B_lead;      % M matrix for frequency dynamics

% Electrical network (same topology), line reactances
X_line = 0.1;               % Ohm
V_rms = 220;                % V
V2_over_X = V_rms^2 / X_line;   % W/rad
% Network Laplacian and susceptance matrix (in kW/rad)
L_net = L_comm;
B_kW = (V2_over_X / 1000) * L_net;   % kW/rad

% Gains
m_f = 50;           % Frequency consensus gain
m_P = 50;           % Active power sharing gain

% Base loads
P_load_nom = [80; 80; 80; 80; 80; 80]; % kW

% Simulation setup
dt = 1e-4;          % 0.1 ms
t_end = 10;         % seconds
f_tol = 0.02;       % Hz, tolerance for restoration

% Compute theoretical delay margin (frequency loop)
lambda_max_M = max(eig(M_f));
tau_max_f = pi / (2 * m_f * lambda_max_M);
tau_below = tau_max_f * 0.9;
tau_above = tau_max_f * 1.5;
fprintf('tau_max_f = %.4f ms\n', tau_max_f*1000);

%% Common initial steady state (only droop control, no DSC)
% Solve for initial frequency
sum_inv_kP = sum(1 ./ kP);
total_load = sum(P_load_nom);
omega_ss = f_ref - total_load / sum_inv_kP;
P_ss = (f_ref - omega_ss) ./ kP;

% Initial phase angles (use pinv to get minimum norm solution)
theta0 = pinv(B_kW) * (P_ss - P_load_nom);

x0 = zeros(N,1);   % initial secondary control integrator states

%% Helper function handles
% Closed-loop dynamics without delay
compute_f = @(x, theta, Load) f_ref + x - kP .* (B_kW * theta + Load);
dynamics_no_delay = @(t, x, theta, Load, enable) deal(...
    enable * (-m_f * M_f * (compute_f(x, theta, Load) - f_ref) ...
             -m_P * L_comm * (kP .* (B_kW * theta + Load))),...
    2*pi * (compute_f(x, theta, Load) - f_ref));

%% ---------- Scenario 1: No delay, load change ----------
t_vec = 0:dt:t_end;
n_steps = length(t_vec);
x = x0; theta = theta0;
Load = P_load_nom;
enable = 0;
f_hist1 = zeros(N, n_steps);
P_hist1 = zeros(N, n_steps);
for k = 1:n_steps
    t_now = t_vec(k);
    if t_now >= 3
        enable = 1;
    end
    % Load changes
    if t_now >= 6 && t_now < 8
        Load(6) = 0;
    else
        Load(6) = P_load_nom(6);
    end
    
    % Record
    f = compute_f(x, theta, Load);
    P = B_kW * theta + Load;
    f_hist1(:,k) = f;
    P_hist1(:,k) = P;
    
    % Euler step
    [dx, dtheta] = dynamics_no_delay(t_now, x, theta, Load, enable);
    x = x + dt * dx;
    theta = theta + dt * dtheta;
end

%% ---------- Scenario 2a: With delay below margin ----------
% Pre-allocate delay buffer
Ndel = ceil(tau_below/dt) + 2;
f_buf = zeros(N, Ndel);
f_buf(:,1) = compute_f(x0, theta0, P_load_nom); % initial f
buf_ptr = 1;

x = x0; theta = theta0;
Load = P_load_nom;
enable = 0;
f_hist2a = zeros(N, n_steps);
for k = 1:n_steps
    t_now = t_vec(k);
    if t_now >= 3
        enable = 1;
    end
    if t_now >= 6 && t_now < 8
        Load(6) = 0;
    else
        Load(6) = P_load_nom(6);
    end
    
    f_now = compute_f(x, theta, Load);
    f_buf(:, buf_ptr) = f_now;
    f_hist2a(:,k) = f_now;
    
    % retrieve delayed frequency
    delay_steps = round(tau_below/dt);
    idx = mod(buf_ptr - delay_steps - 1, Ndel) + 1;
    f_delayed = f_buf(:, idx);
    
    % Delayed frequency control
    u_f_del = enable * (-m_f * M_f * (f_delayed - f_ref));
    u_P = enable * (-m_P * L_comm * (kP .* (B_kW * theta + Load)));
    dx = u_f_del + u_P;
    dtheta = 2*pi * (f_now - f_ref);
    
    x = x + dt * dx;
    theta = theta + dt * dtheta;
    buf_ptr = mod(buf_ptr, Ndel) + 1;
end

%% Scenario 2b: With delay above margin
Ndel = ceil(tau_above/dt) + 2;
f_buf = zeros(N, Ndel);
f_buf(:,1) = compute_f(x0, theta0, P_load_nom);
buf_ptr = 1;

x = x0; theta = theta0;
Load = P_load_nom;
enable = 0;
f_hist2b = zeros(N, n_steps);
for k = 1:n_steps
    t_now = t_vec(k);
    if t_now >= 3
        enable = 1;
    end
    % No load change in delay scenario (or keep load constant)
    % to isolate delay effect, keep load constant
    Load = P_load_nom;
    
    f_now = compute_f(x, theta, Load);
    f_buf(:, buf_ptr) = f_now;
    f_hist2b(:,k) = f_now;
    
    delay_steps = round(tau_above/dt);
    idx = mod(buf_ptr - delay_steps - 1, Ndel) + 1;
    f_delayed = f_buf(:, idx);
    
    u_f_del = enable * (-m_f * M_f * (f_delayed - f_ref));
    u_P = enable * (-m_P * L_comm * (kP .* (B_kW * theta + Load)));
    dx = u_f_del + u_P;
    dtheta = 2*pi * (f_now - f_ref);
    
    x = x + dt * dx;
    theta = theta + dt * dtheta;
    buf_ptr = mod(buf_ptr, Ndel) + 1;
end

%% ---------- Scenario 3: Plug-and-play ----------
% Simulate DG5 cut-out at t=6, re-insert at t=8
% Modification: remove communication links and fix DG5 power to zero while cut
% After cut-out, DG5 does not participate in control nor power generation.
% Approach: modify A_comm and electrical network temporarily.
% For simplicity, we set Load(5)=0 and keep DG5 connected but its droop control
% will force P5=0 by temporarily making its droop coefficient huge? 
% Instead, we treat DG5 as disconnected by manipulating its state.
% We will set x(5) constant during cut-out, and force its power contribution 
% to zero by setting a large impedance to ground? 
% Better: simulate as if node 5 does not exist, i.e., remove it from B and A.
% We'll do this by zeroing out the corresponding rows/cols in B_kW and L_comm,
% but keep vector size N. For time of cut-out, we modify B_kW_mod and L_comm_mod.
x = x0; theta = theta0;
Load = P_load_nom;
enable = 0;
f_hist3 = zeros(N, n_steps);
P_hist3 = zeros(N, n_steps);
for k = 1:n_steps
    t_now = t_vec(k);
    if t_now >= 3
        enable = 1;
    end
    % Handle cut-out and re-insert of DG5
    if t_now >= 6 && t_now < 8
        % DG5 cut-out: remove its electrical and communication connections
        B_kW_mod = B_kW;
        B_kW_mod(5,:) = 0; B_kW_mod(:,5) = 0;
        L_comm_mod = L_comm;
        L_comm_mod(5,:) = 0; L_comm_mod(:,5) = 0;
        % force its own power to zero (no load, no generation)
        Load(5) = 0;
        % prevent x(5) from updating
        x(5) = x(5); % will be overridden by integrating later? need to freeze
    else
        B_kW_mod = B_kW;
        L_comm_mod = L_comm;
        Load(5) = P_load_nom(5);
    end
    
    f = compute_f(x, theta, Load);
    P = B_kW_mod * theta + Load;
    f_hist3(:,k) = f;
    P_hist3(:,k) = P;
    
    % DSC with modified communication
    u_f = enable * (-m_f * (L_comm_mod + B_lead) * (f - f_ref));
    u_P = enable * (-m_P * L_comm_mod * (kP .* P));
    dx = u_f + u_P;
    % During cut-out, prevent update of x(5)
    if t_now >= 6 && t_now < 8
        dx(5) = 0;
    end
    dtheta = 2*pi * (f - f_ref);
    
    x = x + dt * dx;
    theta = theta + dt * dtheta;
end

%% Metric evaluations
% Scenario 1 metrics
% freq_steady_state_error_zero: max abs(f - f_ref) in last 1 second
idx_steady = t_vec > (t_end - 1);
f_steady_err = max(abs(f_hist1(:, idx_steady) - f_ref), [], 'all');
freq_steady_state_error_zero = f_steady_err;

% power_sharing_steady_state_error_zero: max|k_i P_i - k_j P_j|
P_steady = P_hist1(:, idx_steady);
kP_P = kP .* P_steady;
power_sharing_error = max(max(kP_P) - min(kP_P));
power_sharing_steady_state_error_zero = power_sharing_error;

% freq_restoration_time_less_than_0_5s
% Time from DSC enable (t=3) until all frequencies within f_ref +/- f_tol and stay
t_restore = NaN;
in_band = all(abs(f_hist1 - f_ref) < f_tol, 1);
after_enable = t_vec >= 3;
% find first sustained entry
in_band_sustained = false(size(t_vec));
for i = length(t_vec):-1:1
    if in_band(i)
        in_band_sustained(i) = true;
    else
        break;
    end
end
% entry point is the first true in in_band_sustained after enable
candidates = find(in_band_sustained & after_enable, 1);
if ~isempty(candidates)
    t_restore = t_vec(candidates);
end
freq_restoration_time = t_restore - 3;
freq_restoration_time_less_than_0_5s = (freq_restoration_time < 0.5);

% load_change_recovery_time_less_than_0_5s
% Recovery after load reconnection at t=8
% Measure time from t=8 until frequency re-enters tolerance band (and stays)
after_load = t_vec >= 8;
in_band_after = all(abs(f_hist1 - f_ref) < f_tol, 1) & after_load;
% find first sustained true from end
sustained = false(size(t_vec));
for i = length(t_vec):-1:1
    if in_band_after(i)
        sustained(i) = true;
    else
        break;
    end
end
cand = find(sustained & after_load, 1);
if ~isempty(cand)
    t_rec = t_vec(cand);
else
    t_rec = NaN;
end
load_change_recovery_time = t_rec - 8;
load_change_recovery_time_less_than_0_5s = (load_change_recovery_time < 0.5);

% Scenario 2: stability below/above delay margin
idx_final2a = t_vec > (t_end - 2);
f_range_below = max(f_hist2a(:, idx_final2a), [], 'all') - min(f_hist2a(:, idx_final2a), [], 'all');
stable_below_delay_margin = (f_range_below < 0.1);   % nearly steady

idx_final2b = t_vec > (t_end - 2);
f_range_above = max(f_hist2b(:, idx_final2b), [], 'all') - min(f_hist2b(:, idx_final2b), [], 'all');
unstable_above_delay_margin = (f_range_above > 1.0);  % large oscillation

% Scenario 3: plug-and-play stable recovery
% After re-insert at t=8, check final frequency error and power sharing error
idx_final3 = t_vec > (t_end - 1);
f_final_err3 = max(abs(f_hist3(:, idx_final3) - f_ref), [], 'all');
P_final3 = P_hist3(:, idx_final3);
kP_P_final3 = kP .* P_final3;
power_err3 = max(max(kP_P_final3) - min(kP_P_final3));
plug_play_stable_recovery = (f_final_err3 < 0.02) && (power_err3 < 0.01);

%% Save results
results = struct();
results.freq_steady_state_error_zero = freq_steady_state_error_zero;
results.power_sharing_steady_state_error_zero = power_sharing_steady_state_error_zero;
results.freq_restoration_time_less_than_0_5s = freq_restoration_time_less_than_0_5s;
results.load_change_recovery_time_less_than_0_5s = load_change_recovery_time_less_than_0_5s;
results.stable_below_delay_margin = stable_below_delay_margin;
results.unstable_above_delay_margin = unstable_above_delay_margin;
results.plug_play_stable_recovery = plug_play_stable_recovery;

fid = fopen('results.json', 'w');
fwrite(fid, jsonencode(results));
fclose(fid);

% Optional: save figures
figure(1);
plot(t_vec, f_hist1); xlabel('Time (s)'); ylabel('Frequency (Hz)');
title('Scenario 1: No delay'); legend(arrayfun(@(i) sprintf('DG %d',i),1:N,'UniformOutput',false));
saveas(gcf, 'fig_1.png');

figure(2);
plot(t_vec, f_hist2a); title('Scenario 2: \tau < \tau_{max}');
saveas(gcf, 'fig_2.png');

figure(3);
plot(t_vec, f_hist2b); title('Scenario 2: \tau > \tau_{max}');
saveas(gcf, 'fig_3.png');

figure(4);
plot(t_vec, f_hist3); title('Scenario 3: Plug-and-Play');
saveas(gcf, 'fig_4.png');