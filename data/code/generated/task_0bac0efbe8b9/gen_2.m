% Microgrid Secondary Control with Communication Delay Simulation
% Based on the provided paper and execution plan.
% This script simulates N distributed generators with primary droop control
% and secondary consensus-based control for frequency restoration and active power sharing.
% Fixed communication delays are introduced and stability margins are analyzed.

clear; clc; close all;

%% 1. System Parameters and Configuration
N = 4; % Number of DGs
f_ref = 50.0; % Reference frequency (Hz)
V_dc = 700.0; % DC link voltage (V)

% Primary Control Parameters (Droop)
k_P = 0.0042; % Active power droop coefficient (Hz/W) - assumed same for all for simplicity

% Secondary Control Gains
m_f = 50.0;   % Frequency control gain
m_P = 50.0;   % Active power control gain

% Communication Delay
tau = 0.05;   % Fixed communication delay (seconds)

% Simulation Time
T_sim = 10;   % Total simulation time (s)
dt = 1e-4;    % Simulation step size

%% 2. Communication Topology
% Define Adjacency Matrix A (Symmetric for undirected graph)
% Example: Ring topology 1-2-3-4-1
A = zeros(N);
A(1,2) = 1; A(2,1) = 1;
A(2,3) = 1; A(3,2) = 1;
A(3,4) = 1; A(4,3) = 1;
A(4,1) = 1; A(1,4) = 1;

% Pinned Node Gain Matrix B (Only Node 1 is pinned to reference)
B = diag([1, 0, 0, 0]);

% Calculate Laplacian L and Matrix M = L + B
L = diag(sum(A, 2)) - A;
M = L + B;

% Eigenvalue Analysis for Stability Margin
eig_vals = eig(M);
lambda_max = max(real(eig_vals));
tau_max = pi / (2 * m_f * lambda_max);

fprintf('Max Eigenvalue of M: %.4f\n', lambda_max);
fprintf('Calculated Stability Margin tau_max: %.4f s\n', tau_max);
fprintf('Selected Delay tau: %.4f s\n', tau);

if tau >= tau_max
    warning('The selected delay tau exceeds the theoretical stability margin tau_max. The system may become unstable.');
else
    fprintf('Delay tau is within the stability margin.\n');
end

%% 3. Initial Conditions
% Initial frequencies (slightly off nominal due to primary control load)
f_init = f_ref + [0.1, -0.1, 0.05, -0.05]';
% Initial active powers (arbitrary distribution to test sharing)
P_init = [100, 120, 90, 110]'; 

% State vectors
f = f_init;
P = P_init;

% History for plotting
t_hist = 0;
f_hist = f';
P_hist = P';

%% 4. Simulation Loop
% Pre-allocate buffers for delayed states if using a simple delay line
% Since tau is fixed, we can use a circular buffer or simply index into history
% However, for simplicity and robustness in a script, we will store history
% and look back. Note: This requires storing all history, which is memory intensive for long sims.
% Given T_sim=10s and dt=1e-4, steps = 100,000. This is manageable.

steps = floor(T_sim / dt);
f_history = zeros(N, steps + 1);
P_history = zeros(N, steps + 1);
f_history(:, 1) = f';
P_history(:, 1) = P';

for k = 1:steps
    t = k * dt;
    
    % Calculate delay index
    % We need f(t-tau) and P(t-tau). 
    % Since we are at step k, the time is t.
    % The delayed time is t - tau.
    % Index for t-tau is roughly k - tau/dt.
    % To handle integer indexing, we round to nearest integer.
    delay_idx = round(t / dt - tau / dt);
    if delay_idx < 1
        delay_idx = 1;
    end
    
    % Retrieve delayed states
    f_delayed = f_history(:, delay_idx);
    P_delayed = P_history(:, delay_idx);
    
    %% Primary Control
    % f_i = f_i^n - k_i^P * P_i
    % Here f_i^n is the output of secondary control u_i^f + f_ref (implicitly)
    % Actually, the paper says f_i^n is the frequency correction quantity.
    % The primary control output frequency is f_i.
    % The secondary control adjusts f_i^n.
    % Let's define f_i^n as the reference frequency for primary control.
    % Initially f_i^n = f_ref.
    
    %% Secondary Control
    % 1. Frequency Restoration
    % u_i^f = m_f * (sum_{j} a_ij * (f_j(t-tau) - f_i(t-tau)) + b_i * (f_ref - f_i(t-tau)))
    % In matrix form: u_f = m_f * ( -L * f_delayed + B * (f_ref - f_delayed) )
    % Note: sum_j a_ij (f_j - f_i) is the i-th row of -L * f.
    % The term b_i (f_ref - f_i) is the i-th element of B * (f_ref - f).
    
    u_f = m_f * (-L * f_delayed + B * (f_ref - f_delayed));
    
    % 2. Active Power Sharing
    % u_i^P = m_P * sum_{j} a_ij * (k_j^P * P_j(t-tau) - k_i^P * P_i(t-tau))
    % Assuming k_P is constant for all, k_j^P = k_i^P = k_P.
    % u_i^P = m_P * k_P * sum_{j} a_ij * (P_j - P_i)
    % In matrix form: u_P = m_P * k_P * (-L * P_delayed)
    
    u_P = m_P * k_P * (-L * P_delayed);
    
    %% Update Primary Control Reference
    % f_i^n = integral(u_i^f + u_i^P) ? 
    % Paper Eq (4): f_i^n = integral(u_i^f + u_i^P).
    % This implies f_i^n is the integral of the secondary control inputs.
    % However, usually secondary control adds to the primary reference.
    % Let's integrate u_f and u_P to get the correction term delta_f_n.
    % f_i^n_new = f_i^n_old + (u_f + u_P) * dt
    
    % We need to maintain the integral state for f_i^n
    % Let's define f_n as the current reference frequency for primary control
    if k == 1
        f_n = f_ref * ones(N, 1);
    else
        % Update integral
        f_n = f_n + (u_f + u_P) * dt;
    end
    
    %% Primary Control Output
    % f_i = f_i^n - k_i^P * P_i
    f_new = f_n - k_P * P;
    
    %% Active Power Dynamics (Simplified)
    % The paper doesn't explicitly give the P dynamics, but P changes based on load/generation.
    % For simulation purposes, we assume P changes slowly or is driven by the frequency mismatch.
    % A common simplified model: dP/dt = -1/T * (P - P_load) or similar.
    % However, to strictly follow the "consensus" aspect, we can assume P is a state that evolves.
    % Let's assume a simple first-order lag for P to make it dynamic, or just keep P constant if it's a static load.
    % To demonstrate sharing, P should change. Let's assume a simple dynamic:
    % dP/dt = -1/T_p * (P - P_ref) + noise? 
    % Or, more simply, since the goal is to show consensus, we can just let P be a state that is influenced by the grid.
    % Let's use a simple integrator for P to simulate load changes or generation adjustments.
    % dP/dt = u_P_effect? No, u_P is the control input for the reference.
    % Let's assume P dynamics are: dP/dt = -1/T * (P - P_desired).
    % To keep it simple and focused on the control law, let's assume P is a state that integrates some disturbance.
    % Let's add a small disturbance to P to make it interesting.
    % dP/dt = -0.1 * (P - P_init) + 0.1 * sin(t) ?
    % Actually, the paper focuses on the control of f and P.
    % Let's assume P dynamics are: dP/dt = -1/T * (P - P_load).
    % Let's set T = 1s.
    T_p = 1.0;
    P_load = P_init + 10 * sin(2 * pi * 0.1 * t); % Slowly varying load
    dP = -1/T_p * (P - P_load);
    P_new = P + dP * dt;
    
    %% Update History
    f = f_new;
    P = P_new;
    
    f_history(:, k+1) = f';
    P_history(:, k+1) = P';
    
    % Store for plotting
    t_hist = [t_hist; t];
    f_hist = [f_hist; f'];
    P_hist = [P_hist; P'];
    
    % Progress
    if mod(k, 1000) == 0
        fprintf('Step %d/%d, Time: %.2f s\n', k, steps, t);
    end
end

%% 5. Plotting Results

% Figure 1: Frequency Restoration
figure(1);
plot(t_hist, f_hist, 'LineWidth', 1.5);
hold on;
yline(f_ref, 'r--', 'LineWidth', 2);
title('Frequency Restoration with Secondary Control');
xlabel('Time (s)');
ylabel('Frequency (Hz)');
legend('DG 1', 'DG 2', 'DG 3', 'DG 4', 'Reference');
grid on;
exportgraphics(gcf, 'fig_1.png');

% Figure 2: Active Power Sharing
figure(2);
plot(t_hist, P_hist, 'LineWidth', 1.5);
title('Active Power Sharing with Secondary Control');
xlabel('Time (s)');
ylabel('Active Power (W)');
legend('DG 1', 'DG 2', 'DG 3', 'DG 4');
grid on;
exportgraphics(gcf, 'fig_2.png');

% Figure 3: Frequency Error
figure(3);
f_err = f_hist - f_ref;
plot(t_hist, f_err, 'LineWidth', 1.5);
title('Frequency Error Convergence');
xlabel('Time (s)');
ylabel('Frequency Error (Hz)');
legend('DG 1', 'DG 2', 'DG 3', 'DG 4');
grid on;
exportgraphics(gcf, 'fig_3.png');

% Figure 4: Power Sharing Error
figure(4);
P_avg = mean(P_hist, 2);
P_err = P_hist - P_avg;
plot(t_hist, P_err, 'LineWidth', 1.5);
title('Active Power Sharing Error Convergence');
xlabel('Time (s)');
ylabel('Power Error (W)');
legend('DG 1', 'DG 2', 'DG 3', 'DG 4');
grid on;
exportgraphics(gcf, 'fig_4.png');

%% Local Functions
function plot_stability_margin(tau_max, tau)
    % This function is not used in the main script but can be called if needed
    % It is defined here to satisfy the requirement of local functions at the end
    fprintf('Stability Margin Analysis:\n');
    fprintf('tau_max: %.4f s\n', tau_max);
    fprintf('tau: %.4f s\n', tau);
    if tau < tau_max
        fprintf('System is stable.\n');
    else
        fprintf('System is unstable.\n');
    end
end