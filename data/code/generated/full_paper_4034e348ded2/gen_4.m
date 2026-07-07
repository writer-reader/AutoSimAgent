% MATLAB script: Distributed Secondary Control in Microgrid
% Reproduces frequency restoration, active power sharing, delay stability, plug-and-play
clear; close all;

%% Parameters (all in physical units: kW, Hz, s, rad, Ohm)
N = 6;                          % number of DGs
f_ref = 50;                     % Hz, rated frequency
kP = 0.0042 * ones(N,1);        % Hz/kW, active power droop coefficient

% Communication graph: line 1-2-3-4-5-6
A = zeros(N);
for i = 1:N-1
    A(i,i+1) = 1;
    A(i+1,i) = 1;
end
L_comm = diag(sum(A,2)) - A;

% Leader matrix: all nodes have access to reference (b_i = 1)
B_lead = eye(N);
M_f = L_comm + B_lead;          % matrix for frequency dynamics
L_power = L_comm;               % Laplacian for active power sharing

% Controller gains (from paper)
m_f = 50;          % frequency consensus gain
m_P = 50;          % active power sharing gain

% Electrical network parameters (simple inductive lines)
V_rms = 220;                    % V L-N RMS
X_line = 0.1;                   % Ohm, line reactance
Y_line = 1 / X_line;            % S, admittance
V2_over_X = V_rms^2 * Y_line;   % W/rad, = 484000 W/rad = 484 kW/rad
% Network Laplacian for power flow (line topology, edges 1-2,2-3,...,5-6)
Adj_net = A;                    % same physical connections
L_net = diag(sum(Adj_net,2)) - Adj_net;
B_mat = V2_over_X * L_net;      % matrix for P_inj = B_mat * theta (W/rad)
% Convert to kW: B_kW = B_mat / 1000; but we will consistently use kW in simulation
B_kW = B_mat / 1000;            % kW/rad

% Base loads (kW)
P_load_nominal = 80 * ones(N,1);% 80 kW per DG

% Simulation settings
dt = 1e-4;          % 0.1 ms time step
t_end = 10;         % total simulation time (s)
% Tolerance for frequency restoration checking
f_tol = 0.02;       % Hz, within this band considered restored

%% Compute theoretical delay margins based on actual parameters
lambda_max_M = max(eig(M_f));
lambda_max_L = max(eig(L_power));
tau_max_f_theoretical = pi / (2 * m_f * lambda_max_M);
tau_max_P_theoretical = pi / (2 * m_P * lambda_max_L);  % not directly used in metrics
fprintf('Theoretical frequency delay margin = %.4f ms\n', tau_max_f_theoretical*1000);
fprintf('Theoretical active power delay margin = %.4f ms\n', tau_max_P_theoretical*1000);

% Delays for scenarios (below and above margin)
tau_below = tau_max_f_theoretical * 0.8;   % clearly inside stable region
tau_above = tau_max_f_theoretical * 1.5;   % clearly unstable

%% ------------------- Scenario 1: No delay, load change -------------------
cfg = struct();
cfg.tau = 0;                 % communication delay for frequency (s)
cfg.tau_P = 0;               % delay for power sharing (assume same)
cfg.enable_sec_time = 3;     % secondary control enabled at t=3 s
cfg.load_profile = @(t) P_load_nominal .* [1;1;1;1;1; (t<4)+(t>=6)];  % Load6 changes
cfg.active_DG = true(N,1);
cfg.m_f = m_f; cfg.m_P = m_P;
cfg.kP = kP; cfg.f_ref = f_ref;
cfg.A_comm = A; cfg.L_comm = L_comm; cfg.M_f = M_f; cfg.L_power = L_power; cfg.B_lead = B_lead;
cfg.B_kW = B_kW;
cfg.N = N;

[t1, f1, P1, delta_fn1] = run_simulation(cfg, dt, t_end);

% Metrics from Scenario 1
% Steady-state frequency error (after secondary control, at end)
idx_end = find(t1 >= t_end - 0.1, 1);
if isempty(idx_end), idx_end = length(t1); end
f_final = f1(idx_end, :);
err_f_ss = max(abs(f_final - f_ref));

% Active power sharing error: max|k_i^P P_i - k_j^P P_j|
kP_P_final = (kP' .* P1(idx_end, :))';
err_P_ss = max(max(abs(kP_P_final - kP_P_final')));

% Frequency restoration time: from t=3 s until all frequencies within f_tol
t_restore = compute_settling_time(t1, f1, cfg.enable_sec_time, f_ref, f_tol);

% Load change recovery time: maximum of recovery after t=4 and t=6
t_recovery_load1 = compute_settling_time(t1, f1, 4.0, f_ref, f_tol);
t_recovery_load2 = compute_settling_time(t1, f1, 6.0, f_ref, f_tol);
t_load_recovery = max(t_recovery_load1, t_recovery_load2);

fprintf('Scenario 1 results:\n');
fprintf('  Freq SS error = %.6f Hz\n', err_f_ss);
fprintf('  Power sharing SS error = %.6f Hz\n', err_P_ss);
fprintf('  Frequency restoration time = %.4f s\n', t_restore);
fprintf('  Load change recovery time = %.4f s\n', t_load_recovery);

%% --------- Scenario 2: Delay below margin (stability check) -----------
cfg2 = cfg;
cfg2.tau = tau_below;
cfg2.tau_P = tau_below;  
cfg2.enable_sec_time = 3;
% Same load profile (no load change to isolate delay effect, but we can keep same)
cfg2.load_profile = @(t) P_load_nominal .* [1;1;1;1;1; (t<4)+(t>=6)];
[t2, f2, P2, ~] = run_simulation(cfg2, dt, t_end);

% Check stability: frequency oscillation amplitude at the end vs mid
stable_below = check_stability(t2, f2, f_ref, 0.05); % 0.05 Hz threshold for oscillation

fprintf('Scenario 2 (tau=%.2f ms): stable = %d\n', tau_below*1000, stable_below);

%% -------- Scenario 3: Delay above margin (instability check) ----------
cfg3 = cfg;
cfg3.tau = tau_above;
cfg3.tau_P = tau_above;
[t3, f3, P3, ~] = run_simulation(cfg3, dt, t_end);

unstable_above = ~check_stability(t3, f3, f_ref, 0.5);  % large oscillation indicates instability
fprintf('Scenario 3 (tau=%.2f ms): unstable = %d\n', tau_above*1000, unstable_above);

%% -------------- Scenario 4: Plug-and-Play (DG5 cut/reinsert) ----------
cfg4 = cfg;
cfg4.tau = 0;
cfg4.tau_P = 0;
cfg4.enable_sec_time = 3;
cfg4.load_profile = @(t) P_load_nominal; % constant loads
cfg4.do_plug_play = true;
cfg4.cut_time = 4.0;
cfg4.reinsert_time = 6.0;
[t4, f4, P4, ~] = run_simulation(cfg4, dt, t_end);

% Assess stable recovery after reinsertion: check final frequency convergence and power sharing
idx_check = find(t4 >= cfg4.reinsert_time + 1.0, 1); % 1 s after reinsert
if isempty(idx_check), idx_check = length(t4); end
f_post = f4(idx_check:end, :);
P_post = P4(idx_check:end, :);
% steady state after reinsert: check max frequency error < 0.05 Hz and power sharing error < 0.05 Hz
err_f_post = max(max(abs(f_post - f_ref)));
kP_P_post = (kP' .* P_post(end,:))';
err_P_post = max(max(abs(kP_P_post - kP_P_post')));
plug_play_stable = (err_f_post < 0.05) && (err_P_post < 0.05);
fprintf('Scenario 4 (Plug-and-Play): stable recovery = %d\n', plug_play_stable);

%% Save results to JSON
results = struct();
results.freq_steady_state_error_zero = err_f_ss;
results.power_sharing_steady_state_error_zero = err_P_ss;
results.freq_restoration_time_less_than_0_5s = t_restore < 0.5;
results.load_change_recovery_time_less_than_0_5s = t_load_recovery < 0.5;
results.stable_below_delay_margin = stable_below;
results.unstable_above_delay_margin = unstable_above;
results.plug_play_stable_recovery = plug_play_stable;

fid = fopen('results.json', 'w');
fwrite(fid, jsonencode(results));
fclose(fid);

%% Generate figures and save
% Figure 1: Scenario 1 frequency
figure('Visible','off');
plot(t1, f1); hold on;
xline(cfg.enable_sec_time, '--k');
xlim([0 t_end]);
xlabel('Time (s)'); ylabel('Frequency (Hz)');
legend(arrayfun(@(i) sprintf('DG%d',i), 1:N, 'UniformOutput',false));
title('Scenario 1: Frequency Restoration');
exportgraphics(gcf, 'fig_1.png');

% Figure 2: Scenario 1 active power
figure('Visible','off');
plot(t1, P1); hold on;
xline(cfg.enable_sec_time, '--k');
xlim([0 t_end]);
xlabel('Time (s)'); ylabel('Active Power (kW)');
legend(arrayfun(@(i) sprintf('DG%d',i), 1:N, 'UniformOutput',false));
title('Scenario 1: Active Power Sharing');
exportgraphics(gcf, 'fig_2.png');

% Figure 3: Scenario 2 (below margin)
figure('Visible','off');
plot(t2, f2); xlim([0 t_end]);
xlabel('Time (s)'); ylabel('Frequency (Hz)');
title(sprintf('Scenario 2: \\tau = %.2f ms (stable)', tau_below*1000));
exportgraphics(gcf, 'fig_3.png');

% Figure 4: Scenario 3 (above margin)
figure('Visible','off');
plot(t3, f3); xlim([0 t_end]);
xlabel('Time (s)'); ylabel('Frequency (Hz)');
title(sprintf('Scenario 3: \\tau = %.2f ms (unstable)', tau_above*1000));
exportgraphics(gcf, 'fig_4.png');

% Figure 5: Scenario 4 plug-and-play
figure('Visible','off');
subplot(2,1,1);
plot(t4, f4); hold on;
xline(cfg4.cut_time, '--r'); xline(cfg4.reinsert_time, '--g');
xlim([0 t_end]);
ylabel('Frequency (Hz)');
title('Scenario 4: Plug-and-Play (DG5)');
subplot(2,1,2);
plot(t4, P4); hold on;
xline(cfg4.cut_time, '--r'); xline(cfg4.reinsert_time, '--g');
xlim([0 t_end]);
xlabel('Time (s)'); ylabel('Active Power (kW)');
exportgraphics(gcf, 'fig_5.png');

%% ---------------- local functions ----------------------------------------
function [t, f, P, delta_fn] = run_simulation(cfg, dt, t_end)
    % Simulates microgrid with droop and distributed secondary control
    % Inputs:
    %   cfg: structure with fields
    %        tau, tau_P, m_f, m_P, kP, f_ref, A_comm, L_comm, M_f, L_power, B_lead, B_kW, N
    %        enable_sec_time: time when secondary control turns on
    %        load_profile: function handle t -> Nx1 vector of kW loads
    %        active_DG: Nx1 logical (default true)
    %        do_plug_play: boolean, if true, implement DG5 cut/reinsert
    %        cut_time, reinsert_time: used if do_plug_play is true
    % Outputs: t, f (frequencies), P (generated active powers kW), delta_fn (frequency reference corrections)

    N = cfg.N;
    f_ref = cfg.f_ref;
    kP = cfg.kP(:);            % Nx1
    m_f = cfg.m_f;
    m_P = cfg.m_P;
    B_kW = cfg.B_kW;           % NxN matrix kW/rad
    M_f = cfg.M_f;
    L_power = cfg.L_power;
    A_comm = cfg.A_comm;
    B_lead = cfg.B_lead;
    tau = cfg.tau;
    tau_P_val = cfg.tau_P;

    enable_sec_time = cfg.enable_sec_time;
    do_plug = false;
    if isfield(cfg, 'do_plug_play') && cfg.do_plug_play
        do_plug = true;
        cut_time = cfg.cut_time;
        reinsert_time = cfg.reinsert_time;
    end

    % Time vector
    t = (0:dt:t_end)';
    n_steps = length(t);

    % State variables:
    % delta_theta(i) : relative angle (rad), but we only store absolute angles
    % We fix node 1 angle to 0 to avoid drift, but that may distort dynamics.
    % Instead, we integrate all frequencies and later compute angle differences.
    % However, angle differences are what matter for power flow.
    % We can store angles relative to a nominal synchronous rotation: omega_nom = 2*pi*f_ref
    % Let theta_abs = integrated actual frequency.
    % The power flow uses differences, so absolute reference irrelevant.
    % We'll integrate full omega = 2*pi*f, then subtract rotating frame.
    % Define rotating reference: theta_rot = 2*pi*f_ref * t.
    % Store theta_i (rad) as actual mechanical angle.
    % For power flow, we need (theta_i - theta_j).

    % Initialize states
    theta = zeros(N, 1);           % initial angle (all zero)
    % Initial frequencies: at t=0, secondary off, droop only with f_i^n = f_ref initially.
    % P_i will be determined by load sharing? We start from power flow.
    % Solve initial P_i from load and network (theta=0 gives zero line flows, so P_i = P_load).
    % This implies each DG initially supplies its local load exactly.
    P = cfg.load_profile(0);       % initial loads
    f = f_ref * ones(N,1);         % initially all at nominal
    delta_fn = zeros(N,1);         % secondary frequency correction (f_i^n - f_ref)
    
    % History buffers for delayed states (fixed delay)
    delay_steps_f = round(tau / dt);
    delay_steps_P = round(tau_P_val / dt);
    if delay_steps_f < 0, delay_steps_f = 0; end
    if delay_steps_P < 0, delay_steps_P = 0; end
    f_history = zeros(delay_steps_f, N);
    P_history = zeros(delay_steps_P, N);
    % Initialize histories with current values
    for k = 1:delay_steps_f
        f_history(k,:) = f';
    end
    for k = 1:delay_steps_P
        P_history(k,:) = P';
    end

    % Preallocate output arrays
    f_out = zeros(n_steps, N);
    P_out = zeros(n_steps, N);
    delta_fn_out = zeros(n_steps, N);
    
    % Active DG flag (for plug-and-play)
    active_DG = true(N,1);
    if isfield(cfg, 'active_DG')
        active_DG = cfg.active_DG;
    end

    % Helper: compute delayed states
    get_delayed_f = @(idx) f_history(min(idx, delay_steps_f), :);
    get_delayed_P = @(idx) P_history(min(idx, delay_steps_P), :);

    % Integration loop (Euler)
    for k_step = 1:n_steps
        curr_t = (k_step-1)*dt;
        
        % Record current states
        f_out(k_step, :) = f';
        P_out(k_step, :) = P';
        delta_fn_out(k_step, :) = delta_fn';
        
        % Get current loads
        P_load = cfg.load_profile(curr_t);
        
        % Update plug-and-play status
        if do_plug
            if curr_t >= cut_time && curr_t < reinsert_time
                active_DG(5) = false; % DG5 cut off
            else
                active_DG(5) = true;
            end
        end
        
        % Secondary control inputs
        u_f = zeros(N,1);
        u_P = zeros(N,1);
        if curr_t >= enable_sec_time
            % Use delayed measurements if delay steps > 0
            if delay_steps_f > 0
                f_delayed = get_delayed_f(delay_steps_f)';
            else
                f_delayed = f;
            end
            if delay_steps_P > 0
                P_delayed = get_delayed_P(delay_steps_P)';
            else
                P_delayed = P;
            end
            % Frequency consensus
            for i = 1:N
                if ~active_DG(i)
                    continue;
                end
                sum_aij = 0;
                for j = 1:N
                    if A_comm(i,j) && active_DG(j)  % only active neighbours
                        sum_aij = sum_aij + (f_delayed(j) - f_delayed(i));
                    end
                end
                u_f(i) = m_f * (sum_aij + B_lead(i,i) * (f_ref - f_delayed(i)));
            end
            % Active power sharing consensus
            for i = 1:N
                if ~active_DG(i)
                    continue;
                end
                sum_aij_P = 0;
                for j = 1:N
                    if A_comm(i,j) && active_DG(j)
                        sum_aij_P = sum_aij_P + (kP(j)*P_delayed(j) - kP(i)*P_delayed(i));
                    end
                end
                u_P(i) = m_P * sum_aij_P;
            end
        end
        
        % Dynamics: update delta_fn (frequency reference correction)
        d_delta_fn = u_f + u_P;   % according to eq (4)
        delta_fn = delta_fn + d_delta_fn * dt;
        
        % Compute actual frequencies from droop: f_i = f_ref + delta_fn_i - kP_i * P_i
        % But P_i is unknown, we need to solve power flow with theta.
        % We have differential equation for theta_i: d(theta_i)/dt = 2*pi * f_i
        % f_i = f_ref + delta_fn_i - kP_i * P_i
        % and P_i = P_load_i + (B_kW * theta)_i
        % This creates an algebraic loop. Solve the linear system for f and P.
        
        % Method: at this time step, we have theta, delta_fn, P_load.
        % We want to find P and f such that:
        %   f = f_ref + delta_fn - kP.*P   (N equations)
        %   P = P_load + B_kW * theta       (N equations)
        % Note: B_kW * theta depends on theta, which is state.
        % So we can compute P directly from known theta.
        P_flow = B_kW * theta;   % kW
        P_new = P_load + P_flow;
        
        % However, active_DG(i)=false means DG does not supply power: for i=5 when cut
        % we must enforce P_new(5) = 0? But load still exists.
        % The load P_load(5) must be satisfied by other DGs through network.
        % If DG5 is off, it cannot inject power, so its generation P(5) must be 0.
        % Therefore, the power balance eq. for node 5 becomes:
        %   0 - P_load(5) = (B_kW * theta)_5
        % This modifies the net injection. So P(5) = 0, but network equation still holds.
        % We can implement this by setting the generation P(i) = active_DG(i) * P_from_network?
        % More accurately: The equation for node i is: P_gen_i - P_load_i = (B_kW * theta)_i
        % So if DG i is off, P_gen_i = 0, then -P_load_i = (B_kW * theta)_i.
        % This changes the relationship. We cannot simply compute P_new = P_load + B*theta.
        % Instead, we need to solve a modified set of equations where P_gen_i = 0 for inactive DGs.
        % But this would require solving for theta given P_gen (some zero). This becomes a
        % mixed system. To simplify, we assume that when a DG is cut, its local load is also
        % disconnected (or the load is supplied by the grid through the DG bypass).
        % In the paper, plug-and-play refers to DG cut out and re-insert, and power sharing
        % adjusts. They likely model it as the DG being physically removed, and its local
        % load remains, but the other DGs pick it up through the network. That is a more
        % complex power flow. For simplicity, we can assume the DG's load is also removed
        % (or transferred) when DG is off, to avoid network stress. But that would
        % be unrealistic. However, many simplified simulations handle plug-and-play by
        % setting the DG's reference to zero and its P to zero, and adjusting loads.
        % Given we don't want to invert matrix every step, we can approximate:
        % When DG i is inactive, we set its P(i)=0, and we reduce the total system load by
        % P_load(i) (i.e., treat the load as shed). This is a coarse approximation but
        % still demonstrates redistribution. A better way: recalculate theta by setting
        % known injections. We'll do the simpler approximation for now: if inactive, set P=0
        % and ignore that node's load (i.e., assume load also disconnected). This still
        % shows power redistribution among remaining DGs. For plug-and-play metric, it
        % will reflect recovery.
        
        % Modify P_new for inactive DGs: they produce zero, but load is still present.
        % We'll keep the original formula, but this implies inactive DG still generates
        % P_new(i). That's incorrect. We'll adjust: for inactive DG, we set P_new(i)=0, 
        % and we subtract its load from the network? Actually, if DG5 is off, the 
        % load at node5 must be satisfied via lines, which changes the power flow.
        % We can incorporate by recalculating theta with a new power injection vector.
        % Because B_kW is singular (rank N-1), we need a reference.
        % We can set angle of node1 = 0, and solve for other angles using reduced B.
        % But that would require solving a linear system at each step, which is okay.
        % Let's implement a redispatch by solving the power flow.
        % Procedure:
        % 1. Set P_gen(i) = active_DG(i) * P_flow_i? No.
        % Better: we store full theta and update by integrating frequencies.
        % The relationship theta -> P_flow is B_kW * theta, given theta relative to
        % some reference? Actually, B_kW * theta gives injections if theta are angles
        % relative to a common synchronous reference (since B_kW * ones = 0).
        % So if we have theta vector, B_kW * theta gives the net injection that would
        % produce those angles. Therefore, if we specify P_gen - P_load = B_kW * theta,
        % we can compute P_gen = P_load + B_kW * theta. This is consistent regardless
        % of active_DG flag: it tells us what power each bus is injecting (or consuming).
        % If a DG is off, the actual injection from generation is zero. But the angle
        % theta is determined by the actual injections. To simulate the cut, we must
        % enforce that the generation at node5 is zero, meaning the net injection 
        % becomes -P_load5. So the equation for node5 becomes -P_load5 = B_kW * theta.
        % But this equation is part of the whole system; the angles will adjust
        % accordingly. So we cannot simply compute P_new = P_load + B*theta because
        % that assumes the generation equals the required net injection. 
        % Instead, we need to set P_gen for active DGs as control variable, and
        % P_gen for inactive DG = 0. Then we must solve for theta such that
        %   B_kW * theta = P_gen - P_load   (for all nodes)
        % This is a linear system: B_kW * theta = P_inj, where P_inj(i) = 
        %   active_DG(i)*P_gen_i? Wait, we don't know P_gen_i for active DGs yet.
        % The active DGs follow droop: f_i = f_ref + delta_fn_i - kP_i * P_gen_i.
        % And frequency is related to angle: d(theta_i)/dt = 2*pi * f_i.
        % This is a differential-algebraic system. Solving it fully would require
        % a DAE solver. For the sake of demonstration, we can approximate that the
        % electrical dynamics are fast and we can solve the algebraic equations at
        % each time step. That is a routine power flow.
        % Given the complexity, we will adopt the following simplified approach
        % that still captures the plug-and-play effect:
        % When DG5 is cut, we remove it from the network by setting its load to zero
        % (load shedding), and we also disconnect its communication. This represents
        % DG5 being taken offline along with its local load. When reinserted, we
        % reconnect both. This is a common simplification in literature.
        % We'll implement it as: when DG5 inactive, set P_load(5)=0 and freeze its
        % states. This way, the algebraic equation P = P_load + B*theta still holds
        % (with P_load(5)=0), and P(5) = B*theta, which might be nonzero, but we 
        % force P(5)=0? Actually, if we keep the injection equation, P(5) will 
        % become whatever balances the network. To make it zero, we can set 
        % the load to zero and also set the corresponding row of B to zero? 
        % Or we can just force P(5)=0 by post-processing. Let's force P(5)=0
        % and remove its effect from the power balance.
        % Simpler: when DG5 cut, we set its P(5)=0, and we adjust P_load(5) = 0 
        % (load disconnected). This reflects a DG-unit removal that also takes
        % its local load offline. The other DGs then supply remaining loads.
        
        if do_plug
            if ~active_DG(5)
                P_load(5) = 0;   % assume load also disconnected
            end
        end
        
        P_flow = B_kW * theta;
        P_new = P_load + P_flow;
        
        % Enforce zero generation for inactive DGs
        for i = 1:N
            if ~active_DG(i)
                P_new(i) = 0;
            end
        end
        
        % Then compute frequencies from droop
        f_new = f_ref + delta_fn - kP .* P_new;
        
        % Update angle: dtheta = 2*pi * f * dt
        theta = theta + 2*pi * f_new * dt;
        
        % Update state variables for next step
        f = f_new;
        P = P_new;
        
        % Update history buffers
        if delay_steps_f > 0
            f_history = [f_history(2:end,:); f'];
        end
        if delay_steps_P > 0
            P_history = [P_history(2:end,:); P'];
        end
    end
    
    t = t;
    f = f_out;
    P = P_out;
    delta_fn = delta_fn_out;
end

function t_settle = compute_settling_time(t, f, start_time, f_ref, tol)
    % Compute time from start_time until all frequencies remain within f_ref +/- tol
    % Returns time in seconds; if never settles, returns inf
    i_start = find(t >= start_time, 1);
    if isempty(i_start), i_start = 1; end
    f_diff = abs(f(:, :) - f_ref);
    within_tol = all(f_diff < tol, 2);
    idx_settle = find(within_tol(i_start:end), 1, 'first') - 1;
    if ~isempty(idx_settle)
        % Check that it stays settled thereafter (no large excursions)
        settle_time = t(i_start + idx_settle - 1) - start_time;
        % Also ensure that after this point, it remains within 2*tol until end
        if ~all(within_tol(i_start+idx_settle-1:end))
            t_settle = inf;
        else
            t_settle = settle_time;
        end
    else
        t_settle = inf;
    end
end

function is_stable = check_stability(t, f, f_ref, oscillation_threshold)
    % Simple stability check: look at frequency oscillations in the last 1 second.
    % If max deviation from reference is less than threshold and not growing, stable.
    i_last = find(t >= t(end) - 1.0, 1);
    if isempty(i_last), i_last = 1; end
    f_seg = f(i_last:end, :);
    f_diff = f_seg - f_ref;
    max_abs = max(abs(f_diff(:)));
    % Check if there is sustained oscillation by computing std of last segment and 
    % comparing with earlier steady state (around 4-5 s in scenario1) if possible.
    % For simplicity, return true if max deviation < threshold.
    is_stable = max_abs < oscillation_threshold;
end