% MATLAB script for Distributed Secondary Control simulation (R2024b)
% Saves results to current directory: results.json, figures fig_1..3.png

%% Parameters and graph setup
N = 6;                         % number of DGs
f_ref = 50;                    % reference frequency [Hz]
kP = 0.0042 * ones(N,1);      % active droop coefficient [Hz/kW]
m_f = 50;                     % frequency control gain
m_P = 50;                     % active power sharing gain

% Communication graph: line 1-2-3-4-5-6 with leader pinning on DG1
A_comm = zeros(N);
for i = 1:N-1
    A_comm(i,i+1) = 1;
    A_comm(i+1,i) = 1;
end
L_comm = diag(sum(A_comm,2)) - A_comm;
B_lead = diag([1, zeros(1,N-1)]);
M_f = L_comm + B_lead;   % frequency control system matrix
L_power = L_comm;        % power sharing uses Laplacian only

% Compute theoretical delay margins
lambda_max_M = max(eig(M_f));
lambda_max_L = max(eig(L_power));
tau_max_f = pi / (2 * m_f * lambda_max_M);   % theoretical freq delay margin
tau_max_P = pi / (2 * m_P * lambda_max_L);   % theoretical power delay margin
fprintf('Theoretical freq delay margin: %.6f s\n', tau_max_f);
fprintf('Theoretical power delay margin: %.6f s\n', tau_max_P);

% Electrical network (ring topology, identical line reactance)
X_line = 0.1;              % Ohm
% Construct Laplacian for susceptance: B_ij = 1/X, L_net = D - A
A_net = zeros(N);
for i = 1:N
    j = mod(i, N) + 1;
    A_net(i,j) = 1;
    A_net(j,i) = 1;
end
D_net = diag(sum(A_net,2));
L_net_base = (D_net - A_net) / X_line;  % base susceptance matrix [S]
% Convert to kW/rad using nominal voltage (220 V line-line? using 220 Vrms L-N gives Vbase^2)
V_base = 220;            % L-N RMS
L_net_kW = L_net_base * V_base^2 / 1000;   % kW/rad

% Base loads (each DG has local load) and total load
P_load_base = 80 * ones(N,1);   % kW, each DG initially 80 kW => total 480 kW

% DG5 plug-and-play: initially active
active_DG = true(N,1);

% Simulation time settings
dt = 5e-4;        % time step
t_end = 10;
t_vec = 0:dt:t_end;
steps = length(t_vec);

%% Condition 1: No delay, load change at DG6
cfg1.tau = 0;
cfg1.enable_secondary_time = 3;
cfg1.plug_play = false;     % no DG5 removal
cfg1.load_profile = @(t) P_load_base .* (t>=0) .* ...    % base loads all the time
    ([1;1;1;1;1; (t<4)+(t>=6)]);  % DG6 load disconnects at 4s, reconnects at 6s
cfg1.active_DG = true(N,1);
cfg1.L_net_kW = L_net_kW;

[t1, f1, P1] = run_simulation(cfg1, dt, t_end, N, f_ref, kP, m_f, m_P, A_comm, B_lead, L_comm);

% Figure 1: Frequency
figure(1);
plot(t1, f1); xlabel('Time (s)'); ylabel('Frequency (Hz)'); legend(arrayfun(@(i)sprintf('DG%d',i),1:N,'UniformOutput',false)); grid on;
exportgraphics(gcf, 'fig_1.png');

% Compute metrics for scenario 1
% Steady-state errors (last 1 second)
idx_ss = t1 >= max(t1)-1;
f1_ss = mean(f1(:, idx_ss), 2);
freq_steady_state_error = max(abs(f1_ss - f_ref));

kP_P1 = kP .* P1;
kP_P1_ss = mean(kP_P1(:, idx_ss), 2);
power_sharing_error = max(kP_P1_ss) - min(kP_P1_ss);

% Frequency restoration time after DSC enable (t=3s)
t_dsc_enable = 3;
tol_freq = 0.05;   % Hz tolerance band
idx_enable = find(t1 >= t_dsc_enable, 1);
freq_error = abs(f1 - f_ref);
settled_time = NaN;
for i = idx_enable:length(t1)
    if all(freq_error(:, i:end) < tol_freq, 'all')
        settled_time = t1(i) - t_dsc_enable;
        break;
    end
end
if isnan(settled_time)
    settled_time = inf;
end

% Load change recovery time (after 4s)
t_load_change = 4;
idx_load = find(t1 >= t_load_change, 1);
recovery_time_load = NaN;
for i = idx_load:length(t1)
    if all(freq_error(:, i:end) < tol_freq, 'all')
        recovery_time_load = t1(i) - t_load_change;
        break;
    end
end
if isnan(recovery_time_load)
    recovery_time_load = inf;
end

%% Condition 2: Communication delay (stable below margin, unstable above)
% Sub-scenario 2a: τ = 5 ms (< τ_max_f ≈ 7.6 ms)
cfg2a = cfg1;
cfg2a.tau = 0.005;  % 5 ms
[t2a, f2a, P2a] = run_simulation(cfg2a, dt, t_end, N, f_ref, kP, m_f, m_P, A_comm, B_lead, L_comm);

% Sub-scenario 2b: τ = 15 ms (> τ_max_f)
cfg2b = cfg1;
cfg2b.tau = 0.015;  % 15 ms
[t2b, f2b, P2b] = run_simulation(cfg2b, dt, t_end, N, f_ref, kP, m_f, m_P, A_comm, B_lead, L_comm);

% Judge stability based on final oscillations
idx_ss2 = t2a >= max(t2a)-1;
f2a_ss_std = std(f2a(:, idx_ss2), 0, 2);
stable_below = all(f2a_ss_std < 0.1);  % small oscillations indicate stable

idx_ss2b = t2b >= max(t2b)-1;
f2b_ss_std = std(f2b(:, idx_ss2b), 0, 2);
unstable_above = any(f2b_ss_std > 0.5); % large oscillations indicate unstable

% Figure 2: stable delay case
figure(2);
subplot(2,1,1); plot(t2a, f2a); title('Frequency with \tau = 5 ms'); xlabel('Time (s)'); ylabel('Hz'); grid on;
subplot(2,1,2); plot(t2b, f2b); title('Frequency with \tau = 15 ms'); xlabel('Time (s)'); ylabel('Hz'); grid on;
exportgraphics(gcf, 'fig_2.png');

%% Condition 3: Plug-and-play DG5
cfg3.tau = 0;
cfg3.enable_secondary_time = 3;
cfg3.plug_play = true;      % DG5 cut out at 5s, reinsert at 7s
cfg3.load_profile = @(t) P_load_base;  % constant load
cfg3.active_DG = true(N,1);
cfg3.L_net_kW = L_net_kW;

[t3, f3, P3] = run_simulation(cfg3, dt, t_end, N, f_ref, kP, m_f, m_P, A_comm, B_lead, L_comm);

% Figure 3
figure(3);
subplot(2,1,1); plot(t3, f3); title('Frequency with plug-and-play DG5'); xlabel('Time (s)'); ylabel('Hz'); grid on; legend(arrayfun(@(i)sprintf('DG%d',i),1:N,'UniformOutput',false));
subplot(2,1,2); plot(t3, kP.*P3); title('kP*P'); xlabel('Time (s)'); grid on;
exportgraphics(gcf, 'fig_3.png');

% Check plug-and-play stable recovery: after reinsertion (7s) frequencies converge and power sharing resumes
idx_pp_ss = t3 >= max(t3)-1;
f3_ss_std = std(f3(:, idx_pp_ss), 0, 2);
kP_P3 = kP .* P3;
kP_P3_ss = mean(kP_P3(:, idx_pp_ss), 2);
plug_play_ok = all(f3_ss_std < 0.1) && (max(kP_P3_ss) - min(kP_P3_ss) < 0.1);

%% Write results.json
results.freq_steady_state_error_zero = freq_steady_state_error;
results.power_sharing_steady_state_error_zero = power_sharing_error;
results.freq_restoration_time_less_than_0_5s = settled_time;
results.load_change_recovery_time_less_than_0_5s = recovery_time_load;
results.stable_below_delay_margin = stable_below;
results.unstable_above_delay_margin = unstable_above;
results.plug_play_stable_recovery = plug_play_ok;

fid = fopen('results.json', 'w');
fwrite(fid, jsonencode(results));
fclose(fid);

disp('Results saved to results.json');

%% Local functions

function [t, f, P] = run_simulation(cfg, dt, t_end, N, f_ref, kP, m_f, m_P, A_comm, B_lead, L_comm)
    % Simulation of microgrid with distributed secondary control
    % tau = cfg.tau;
    % enable_secondary_time = cfg.enable_secondary_time;
    % plug_play: logical flag
    % load_profile: function handle @(t) returning Nx1 load vector [kW]
    % L_net_kW: network susceptance matrix [kW/rad]

    tau = cfg.tau;
    t_enable = cfg.enable_secondary_time;
    plug_play = cfg.plug_play;
    load_fcn = cfg.load_profile;
    L_net_kW = cfg.L_net_kW;

    % Time vector
    t_vec = 0:dt:t_end;
    steps = length(t_vec);
    
    % History buffers for delayed variables
    if tau > 0
        hist_len = ceil(tau / dt) + 1;
        f_hist = zeros(N, hist_len);
        kP_P_hist = zeros(N, hist_len);
    else
        hist_len = 1;
        f_hist = zeros(N, 1);
        kP_P_hist = zeros(N, 1);
    end
    hist_idx = 1;

    % State variables: theta (angle deviations in rad) and f_n (secondary freq correction)
    theta = zeros(N, 1);
    f_n = f_ref * ones(N, 1);   % secondary control reference starts at f_ref

    % Storage for outputs
    f = zeros(N, steps);
    P = zeros(N, steps);

    % Active DG mask
    active_DG = true(N,1);
    
    % Dynamic network matrix (will be updated during plug-and-play)
    L_net_active = L_net_kW;

    for k = 1:steps
        t_now = t_vec(k);
        
        % Plug-and-play events
        if plug_play
            if t_now >= 5 && t_now < 7 % DG5 cut out
                active_DG(5) = false;
            else
                active_DG(5) = true;
            end
            % Rebuild network Laplacian according to active DGs
            % Remove rows/cols of inactive DGs from L_net, keeping size N but zero them
            % For simplicity we zero the row/col of inactive nodes and adjust diagonal so that it remains Laplacian.
            % Here we rebuild L_net_active from base ring, then zero out inactive nodes.
            L_full = L_net_kW;
            active = active_DG;
            % Set rows/cols of inactive to zero, and adjust remaining diagonal to preserve power balance property
            L_active = L_full;
            for i = 1:N
                if ~active(i)
                    L_active(i,:) = 0;
                    L_active(:,i) = 0;
                end
            end
            % Restore diagonal to maintain sum of row = 0 for active nodes (optional but helpful)
            for i = 1:N
                if active(i)
                    L_active(i,i) = -sum(L_active(i,:)) + L_active(i,i); % cancels off-diag changes
                end
            end
            L_net_active = L_active;
        else
            L_net_active = L_net_kW;
        end

        % Load vector
        P_load = load_fcn(t_now);
        
        % Compute P_inj based on theta and active network
        P_inj = L_net_active * theta;  % [kW]
        
        % Generated power: P_gen = P_load + P_inj (for active DGs; inactive DGs have zero generation)
        P_gen = P_load + P_inj;
        P_gen(~active_DG) = 0;
        
        % Actual frequency: f_act = f_n - kP.*P_gen
        f_act = f_n - kP .* P_gen;
        
        % Store current frequency and kP*P for history
        f_hist(:, hist_idx) = f_act;
        kP_P = kP .* P_gen;
        kP_P_hist(:, hist_idx) = kP_P;
        
        % Retrieve delayed values
        if tau > 0
            delay_steps = round(tau / dt);
            idx_delayed = mod(hist_idx - delay_steps - 1, hist_len) + 1;
            f_delayed = f_hist(:, idx_delayed);
            kP_P_delayed = kP_P_hist(:, idx_delayed);
        else
            f_delayed = f_act;
            kP_P_delayed = kP_P;
        end

        % Secondary control only after t_enable
        if t_now >= t_enable
            % Frequency control u_f
            u_f = zeros(N,1);
            for i = 1:N
                if active_DG(i)
                    neighbor_sum = 0;
                    for j = 1:N
                        if A_comm(i,j) ~= 0
                            neighbor_sum = neighbor_sum + A_comm(i,j) * (f_delayed(j) - f_delayed(i));
                        end
                    end
                    u_f(i) = m_f * (neighbor_sum + B_lead(i,i) * (f_ref - f_delayed(i)));
                end
            end
            % Active power sharing control u_P
            u_P = zeros(N,1);
            for i = 1:N
                if active_DG(i)
                    sum_P = 0;
                    for j = 1:N
                        if A_comm(i,j) ~= 0
                            sum_P = sum_P + A_comm(i,j) * (kP_P_delayed(j) - kP_P_delayed(i));
                        end
                    end
                    u_P(i) = m_P * sum_P;   % no pinning for power sharing
                end
            end
            
            % Secondary correction derivative: d(f_n)/dt = u_f + u_P
            df_n = u_f + u_P;
        else
            df_n = zeros(N,1);
        end
        
        % Integration of states using forward Euler (small dt)
        % theta derivative: d(theta)/dt = 2*pi*(f_act - f_ref)
        dtheta = 2 * pi * (f_act - f_ref);
        theta = theta + dt * dtheta;
        f_n = f_n + dt * df_n;
        
        % Log
        f(:, k) = f_act;
        P(:, k) = P_gen;
        
        % Advance history pointer
        if tau > 0
            hist_idx = mod(hist_idx, hist_len) + 1;
        end
    end
    t = t_vec;
end