% MATLAB script for Distributed Secondary Control simulation
% Assumes outdir is defined (not used; save to current directory)

%% Parameters
N = 6;                  % number of DGs
f_ref = 50;             % reference frequency [Hz]
kP = 0.0042 * ones(N,1); % active droop coeff [Hz/kW]
m_f = 50;               % frequency control gain
m_P = 50;               % active power sharing gain

% Communication graph: line 1-2-3-4-5-6, leader pinning on DG1
A = zeros(N);
for i = 1:N-1
    A(i,i+1) = 1;
    A(i+1,i) = 1;
end
D = diag(sum(A,2));
L_comm = D - A;        % Laplacian
B_lead = diag([1, zeros(1,N-1)]); % pinning matrix
M_f = L_comm + B_lead;

% Theoretical delay margins
lambda_max_M = max(eig(M_f));
lambda_max_L = max(eig(L_comm));
tau_max_f = pi / (2 * m_f * lambda_max_M);   % frequency loop delay margin
tau_max_P = pi / (2 * m_P * lambda_max_L);   % active power loop (not used directly)
fprintf('Theoretical freq delay margin: %.4f s\n', tau_max_f);
fprintf('Theoretical power delay margin: %.4f s\n', tau_max_P);

% Electrical parameters
V_nom = 220;           % nominal phase voltage (V)
X_line = 0.1;          % line reactance (Ohm)
C_pow = V_nom^2 / X_line;  % coefficient for P_inj = C_pow * L_net * delta [W/rad]
C_pow_kW = C_pow / 1000;   % [kW/rad]

% Build network susceptance matrix (line graph: 1-2-3-4-5-6-1 ring)
L_net_base = zeros(N);
for i = 1:N
    % ring connections
    j1 = mod(i, N) + 1;
    j2 = mod(i-2, N) + 1;
    L_net_base(i, i) = 2 * (1/X_line);  % diagonal = degree * 1/X
    L_net_base(i, j1) = -1/X_line;
    L_net_base(i, j2) = -1/X_line;
end
% Convert to kW/rad
L_net_kW = L_net_base * V_nom^2 / 1000; % matrix form: P_inj(kW) = L_net_kW * delta(rad)

% Simulation common settings
dt = 5e-4;            % 0.5 ms time step
t_end = 10;
steps = round(t_end / dt);
t_vec = 0:dt:t_end;

%% Scenario 1: No delay, load change
cfg1.tau = 0;
cfg1.enable_secondary_time = 3;
cfg1.load_change_time = 4;    % disconnect
cfg1.load_restore_time = 6;   % reconnect
cfg1.plug_play = false;
cfg1.P_load_nominal = 480;    % kW
cfg1.L_net = L_net_kW;
cfg1.C_pow_kW = C_pow_kW;
[t1, f1, P1, kP_P1] = run_simulation(cfg1);

% Compute steady-state errors (last 1 second)
idx_ss = t1 >= 9;
f1_ss = mean(f1(:, idx_ss), 2);
max_freq_err_ss = max(abs(f1_ss - f_ref));

kP_P1_ss = mean(kP_P1(:, idx_ss), 2);
max_share_err_ss = max(max(kP_P1_ss) - min(kP_P1_ss));  % max|k_i P_i - k_j P_j|

% Frequency restoration time after DSC enable
t_dsc_enable = 3;
tolerance = 0.05; % Hz
freq_err = abs(f1 - f_ref);
for idx = find(t1 >= t_dsc_enable, 1):length(t1)
    if all(freq_err(:, idx:end) < tolerance, 'all')
        t_settle = t1(idx);
        break;
    end
end
freq_restore_time = t_settle - t_dsc_enable;

% Load change recovery time (after load reconnection at t=6)
t_load_restore = 6;
for idx = find(t1 >= t_load_restore, 1):length(t1)
    if all(freq_err(:, idx:end) < tolerance, 'all')
        t_recover = t1(idx);
        break;
    end
end
load_recovery_time = t_recover - t_load_restore;

% Plots
figure(1); 
subplot(2,1,1); plot(t1, f1); title('Scenario 1: Frequencies'); xlabel('Time (s)'); ylabel('Hz'); grid on;
subplot(2,1,2); plot(t1, kP_P1); title('k^P * P'); xlabel('Time (s)'); grid on;
exportgraphics(gcf, 'fig_1.png');

%% Scenario 2: Delay below margin (tau < tau_max_f)
cfg2 = cfg1;
cfg2.tau = 0.9 * tau_max_f;   % e.g., 6.84 ms if margin 7.6 ms
[t2, f2, P2, kP_P2] = run_simulation(cfg2);

% Stability check: observe last 1 s peak-to-peak of frequency
idx_last = t2 >= 9;
f_pp = max(f2(:, idx_last), [], 2) - min(f2(:, idx_last), [], 2);
stable_below = all(f_pp < 0.1);  % stable if peak-to-peak < 0.1 Hz

figure(2);
subplot(2,1,1); plot(t2, f2); title(sprintf('Scenario 2: Freq with delay=%.2f ms', cfg2.tau*1e3));
subplot(2,1,2); plot(t2, kP_P2); title(sprintf('k^P*P, delay=%.2f ms', cfg2.tau*1e3));
exportgraphics(gcf, 'fig_2.png');

%% Scenario 3: Delay above margin (tau > tau_max_f)
cfg3 = cfg1;
cfg3.tau = 1.1 * tau_max_f;   % e.g., 8.36 ms
[t3, f3, P3, kP_P3] = run_simulation(cfg3);

idx_last3 = t3 >= 9;
f_pp3 = max(f3(:, idx_last3), [], 2) - min(f3(:, idx_last3), [], 2);
unstable_above = any(f_pp3 > 0.2);  % consider unstable if oscillation large

figure(3);
subplot(2,1,1); plot(t3, f3); title(sprintf('Scenario 3: Freq with delay=%.2f ms', cfg3.tau*1e3));
subplot(2,1,2); plot(t3, kP_P3); title(sprintf('k^P*P, delay=%.2f ms', cfg3.tau*1e3));
exportgraphics(gcf, 'fig_3.png');

%% Scenario 4: Plug-and-play (no delay)
cfg4 = cfg1;
cfg4.tau = 0;
cfg4.load_change_time = inf;    % no load change in this test
cfg4.load_restore_time = inf;
cfg4.plug_play = true;
cfg4.DG5_cut_time = 5;
cfg4.DG5_reinsert_time = 8;
[t4, f4, P4, kP_P4] = run_simulation(cfg4);

% Check recovery after re-insert: peak-to-peak in last second
idx_last4 = t4 >= 9;
f_pp4 = max(f4(:, idx_last4), [], 2) - min(f4(:, idx_last4), [], 2);
plug_play_stable = all(f_pp4 < 0.1);

figure(4);
subplot(2,1,1); plot(t4, f4); title('Scenario 4: Plug-and-play frequencies');
subplot(2,1,2); plot(t4, kP_P4); title('k^P*P');
exportgraphics(gcf, 'fig_4.png');

%% Assemble results and write JSON
results.freq_steady_state_error_zero = max_freq_err_ss;
results.power_sharing_steady_state_error_zero = max_share_err_ss;
results.freq_restoration_time_less_than_0_5s = freq_restore_time;
results.load_change_recovery_time_less_than_0_5s = load_recovery_time;
results.stable_below_delay_margin = stable_below;
results.unstable_above_delay_margin = unstable_above;
results.plug_play_stable_recovery = plug_play_stable;

fid = fopen('results.json', 'w');
fwrite(fid, jsonencode(results));
fclose(fid);

%% Local functions
function [t_out, f_out, P_out, kP_P_out] = run_simulation(cfg)
    % Extract parameters
    N = 6;
    f_ref = 50;
    kP = 0.0042 * ones(N,1);
    m_f = 50;
    m_P = 50;
    dt = 5e-4;
    t_end = 10;
    steps = round(t_end / dt);
    t_vec = 0:dt:t_end;
    
    tau = cfg.tau;
    t_enable_sec = cfg.enable_secondary_time;
    t_load_off = cfg.load_change_time;
    t_load_on = cfg.load_restore_time;
    P_load_nom = cfg.P_load_nominal;
    L_net = cfg.L_net;
    C_pow_kW = cfg.C_pow_kW;
    plug_play = cfg.plug_play;
    if plug_play
        t_cut = cfg.DG5_cut_time;
        t_reinsert = cfg.DG5_reinsert_time;
    end
    
    % Communication graph (line 1-2-3-4-5-6) and pinning
    A_comm = zeros(N);
    for i = 1:N-1
        A_comm(i,i+1) = 1;
        A_comm(i+1,i) = 1;
    end
    b_lead = [1; zeros(N-1,1)];
    
    % History buffer for delayed signals
    if tau > 0
        hist_len = ceil(tau / dt) + 2;
    else
        hist_len = 2;  % minimal
    end
    buf_f = f_ref * ones(N, hist_len);
    buf_kP = zeros(N, hist_len);
    buf_idx = 1; % current write pointer (modulo)
    
    % State variables
    delta = zeros(N,1);    % voltage angles [rad]
    x_f = zeros(N,1);      % frequency secondary integral
    x_p = zeros(N,1);      % active power secondary integral
    P_prev = P_load_nom/N * ones(N,1);  % initial guess
    
    % Storage arrays
    save_steps = min(10000, steps);
    out_f = zeros(N, save_steps);
    out_P = zeros(N, save_steps);
    out_kP_P = zeros(N, save_steps);
    out_t = zeros(1, save_steps);
    save_idx = 0;
    save_skip = max(1, floor(steps / save_steps));
    
    % Main loop
    for k = 1:steps
        t = (k-1) * dt;
        
        % Events
        sec_enabled = (t >= t_enable_sec);
        % Load
        if t >= t_load_off && t < t_load_on
            P_load = 0;
        else
            P_load = P_load_nom;
        end
        % Plug-and-play: isolate DG5
        if plug_play && t >= t_cut && t < t_reinsert
            DG5_active = false;
        else
            DG5_active = true;
        end
        
        % Modify network matrix for DG5 isolation
        L_net_cur = L_net;
        if ~DG5_active
            % disconnect node 5 (index=5) by large diagonal
            L_net_cur(5,:) = 0;
            L_net_cur(:,5) = 0;
            L_net_cur(5,5) = 1e6;  % large grounding to fix angle
        end
        
        % Update A_comm for DG5 if not active
        A_cur = A_comm;
        if ~DG5_active
            A_cur(5,:) = 0;
            A_cur(:,5) = 0;
        end
        L_cur = diag(sum(A_cur,2)) - A_cur;
        
        % Secondary reference
        f_n = f_ref + sec_enabled * (x_f + x_p);
        
        % Local frequencies via droop (using previous P)
        f_local = f_n - kP .* P_prev;
        
        % Integrate angles
        delta = delta + dt * 2 * pi * f_local;
        
        % Power injection from network
        P_inj = L_net_cur * delta;  % kW
        % Node generation = injection + load
        P_new = P_inj;
        P_new(6) = P_new(6) + P_load;  % load at node 6
        if ~DG5_active
            % DG5 cut out => set its generation to zero
            P_new(5) = 0;
        end
        P_prev = P_new;
        
        % Retrieve delayed values
        if tau > 0
            delay_steps = round(tau / dt);
            % index of time t - tau in buffer
            idx_del = mod(buf_idx - delay_steps - 1, hist_len) + 1;
            f_del = buf_f(:, idx_del);
            kP_P_del = buf_kP(:, idx_del);
        else
            f_del = f_local;
            kP_P_del = kP .* P_new;
        end
        
        % Secondary control inputs
        if sec_enabled
            % Frequency
            diff_f = A_cur * (f_del - f_local'); % this needs to be computed elementwise
            % Efficient: sum over neighbors
            u_f = zeros(N,1);
            for i = 1:N
                neighbors = find(A_cur(i,:));
                sum_diff = sum(f_del(neighbors) - f_del(i));
                u_f(i) = m_f * (sum_diff + b_lead(i) * (f_ref - f_del(i)));
            end
            
            % Active power
            kP_P_vec = kP .* P_new;
            u_p = zeros(N,1);
            for i = 1:N
                neighbors = find(A_cur(i,:));
                sum_diff = sum(kP_P_del(neighbors) - kP_P_del(i));
                u_p(i) = m_P * sum_diff;
            end
        else
            u_f = zeros(N,1);
            u_p = zeros(N,1);
        end
        
        % Integrate
        x_f = x_f + dt * u_f;
        x_p = x_p + dt * u_p;
        
        % Store current values to buffer
        buf_f(:, mod(buf_idx-1, hist_len) + 1) = f_local;
        buf_kP(:, mod(buf_idx-1, hist_len) + 1) = kP .* P_new;
        buf_idx = mod(buf_idx, hist_len) + 1;
        
        % Record data
        if mod(k-1, save_skip) == 0
            save_idx = save_idx + 1;
            out_t(save_idx) = t;
            out_f(:, save_idx) = f_local;
            out_P(:, save_idx) = P_new;
            out_kP_P(:, save_idx) = kP .* P_new;
        end
    end
    
    % Trim outputs
    t_out = out_t(1:save_idx);
    f_out = out_f(:, 1:save_idx);
    P_out = out_P(:, 1:save_idx);
    kP_P_out = out_kP_P(:, 1:save_idx);
end