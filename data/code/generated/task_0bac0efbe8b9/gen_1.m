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
% Initial active powers (arbitrary distribution)
P_init = [100, 120, 90, 110]';

% State vectors
f = f_init;
P = P_init;

% History storage
t_hist = 0;
f_hist = f';
P_hist = P';

%% 4. Simulation Loop
num_steps = round(T_sim / dt);

% Pre-allocate delay buffers for f and P
% We store the history of states to simulate fixed delay
% Buffer size needs to be large enough to cover tau
buffer_len = round(tau / dt) + 1;
f_buffer = zeros(N, buffer_len);
P_buffer = zeros(N, buffer_len);
buffer_idx = 1;

for step = 1:num_steps
    t = (step - 1) * dt;
    
    % 1. Retrieve delayed states from buffer
    % The state at t-tau is the value written 'buffer_len' steps ago
    % Since we update buffer at end of step, current buffer_idx points to next write
    % So the oldest value is at index 1 if we fill sequentially, 
    % but let's use a circular buffer or simple shift. 
    % Simple approach: shift array.
    
    % Get delayed values: f_delayed = f(t-tau)
    % In our buffer, index 1 is the oldest.
    f_delayed = f_buffer(:, 1);
    P_delayed = P_buffer(:, 1);
    
    % 2. Primary Control Calculation
    % f_i^n = f_i - k_P * P_i
    % Note: The paper defines f_i = f_i^n - k_P * P_i, so f_i^n = f_i + k_P * P_i
    % However, usually primary control sets the frequency based on power.
    % Let's follow Eq (2): f_i = f_i^n - k_P * P_i.
    % Here f_i is the actual frequency output. f_i^n is the reference from secondary.
    % So, actual_frequency = secondary_reference - droop_term.
    
    % 3. Secondary Control Calculation
    % Frequency Restoration: u_i^f = m_f * (sum(a_ij * (f_j_delayed - f_i_delayed)) + b_i * (f_ref - f_i_delayed))
    % This can be written in matrix form: u_f = m_f * ( -L * f_delayed - B * f_delayed + B * f_ref_vec )
    % Wait, sum(a_ij * (f_j - f_i)) is the Laplacian term.
    % Specifically, (L * f)_i = sum_j a_ij * (f_i - f_j).
    % The term in Eq (7) is sum a_ij (f_j - f_i) = - sum a_ij (f_i - f_j) = -(L f)_i.
    % So u_f = m_f * ( -L * f_delayed - B * f_delayed + B * f_ref_vec )
    % u_f = -m_f * (L + B) * f_delayed + m_f * B * f_ref_vec
    % u_f = -m_f * M * f_delayed + m_f * B * f_ref_vec
    
    f_ref_vec = f_ref * ones(N, 1);
    u_f = -m_f * M * f_delayed + m_f * B * f_ref_vec;
    
    % Active Power Sharing: u_i^P = m_P * sum(a_ij * (k_P * P_j - k_P * P_i))
    % Let kP_P = k_P * P.
    % u_P = m_P * ( -L * (k_P * P_delayed) )
    kP_P_delayed = k_P * P_delayed;
    u_P = -m_P * L * kP_P_delayed;
    
    % 4. Update Frequency Reference (Secondary Output)
    % The secondary control outputs corrections to the frequency reference.
    % f_i^n_new = f_i^n_old + u_f + u_P ? 
    % Looking at Eq (4): f_i^n = integral(u_f + u_P).
    // In discrete time: f_i^n(t) = f_i^n(t-dt) + dt * (u_f_i + u_P_i)
    
    % We need to maintain the state of f^n (the secondary reference)
    % Let's define a state variable fn for the secondary reference frequency
    if step == 1
        fn = f_init; % Initialize secondary reference to initial frequency
    else
        % Update fn based on integral of control inputs
        fn = fn + dt * (u_f + u_P);
    end
    
    % 5. Calculate Actual Frequency (Primary Control)
    % f_i = f_i^n - k_P * P_i
    f_actual = fn - k_P * P;
    
    % 6. Update Active Power Dynamics
    // The paper doesn't explicitly give the power dynamics equation (e.g., P_dot = ...).
    // However, Eq (3) says k_P * dot(P) = u_P.
    // So dot(P) = u_P / k_P.
    // This implies the power controller directly dictates the rate of change of power.
    // This is a simplified model often used in consensus control papers.
    
    dot_P = u_P / k_P;
    P = P + dt * dot_P;
    
    % 7. Update Frequency State for next step
    // The actual frequency f_actual is what is measured.
    // For the next step's delayed feedback, we need to store the measured frequency.
    // The measured frequency is f_actual.
    
    % Update buffers
    f_buffer(:, 1:end-1) = f_buffer(:, 2:end);
    f_buffer(:, end) = f_actual;
    
    P_buffer(:, 1:end-1) = P_buffer(:, 2:end);
    P_buffer(:, end) = P;
    
    % Store history
    t_hist = [t_hist; t];
    f_hist = [f_hist; f_actual'];
    P_hist = [P_hist; P'];
end

%% 5. Visualization and Analysis

% Figure 1: Frequency Restoration
figure('Name', 'Frequency Restoration', 'NumberTitle', 'off');
plot(t_hist, f_hist, 'LineWidth', 1.5);
hold on;
yline(f_ref, 'r--', 'Reference Frequency');
xlabel('Time (s)');
ylabel('Frequency (Hz)');
title('Frequency Restoration with Communication Delay');
legend(arrayfun(@(i) sprintf('DG %d', i), 1:N, 'UniformOutput', false));
grid on;
exportgraphics(gcf, 'fig_1.png');

% Figure 2: Active Power Sharing
figure('Name', 'Active Power Sharing', 'NumberTitle', 'off');
plot(t_hist, P_hist, 'LineWidth', 1.5);
xlabel('Time (s)');
ylabel('Active Power (W)');
title('Active Power Sharing with Communication Delay');
legend(arrayfun(@(i) sprintf('DG %d', i), 1:N, 'UniformOutput', false));
grid on;
exportgraphics(gcf, 'fig_2.png');

% Figure 3: Frequency Error Convergence
figure('Name', 'Frequency Error', 'NumberTitle', 'off');
f_err = f_hist - f_ref;
plot(t_hist, f_err, 'LineWidth', 1.5);
xlabel('Time (s)');
ylabel('Frequency Error (Hz)');
title('Frequency Error Convergence');
legend(arrayfun(@(i) sprintf('DG %d Error', i), 1:N, 'UniformOutput', false));
grid on;
exportgraphics(gcf, 'fig_3.png');

% Figure 4: Power Sharing Error
figure('Name', 'Power Sharing Error', 'NumberTitle', 'off');
% Error from average power
P_avg = mean(P_hist, 2);
P_err = P_hist - P_avg;
plot(t_hist, P_err, 'LineWidth', 1.5);
xlabel('Time (s)');
ylabel('Power Deviation from Average (W)');
title('Active Power Sharing Error');
legend(arrayfun(@(i) sprintf('DG %d Deviation', i), 1:N, 'UniformOutput', false));
grid on;
exportgraphics(gcf, 'fig_4.png');

fprintf('Simulation completed. Figures saved as fig_1.png, fig_2.png, fig_3.png, fig_4.png\n');

%% Local Functions
% No local functions needed for this script as all logic is inline.