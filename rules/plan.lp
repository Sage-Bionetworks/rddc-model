% Planning from the current state, on top of engine.lp and route.lp.
%
% Input facts, besides those of route.lp
%   done(X, T, W).   step T of file X ran (or is running): it is part of the route
%   active(X).       file X can take new steps (nothing running or failed)
%
% For each active file, choose the shortest continuation to its target that breaks no
% rule. A file with no such continuation is stuck; the orchestrator reports it. Ties
% go to the continuation whose workflows have the lowest total priority (wprio), then
% scripts/orchestrate.py fails rather than pick one.

#const horizon = 12.

go(X, T, W) :- done(X, T, W).
ran(X, N) :- file(X, _, _, _, _), N = #count { T : done(X, T, _) }.
{ go(X, T, W) : step(P, St, W, _) } 1 :-
    active(X), fprof(X, P), at(X, St, T), ran(X, N), T >= N, T < horizon, not at_goal(X, T).

reached(X) :- route_end(X, T), at_goal(X, T).
stuck(X) :- active(X), not reached(X).
:- rviolation(R, _, _), R != not_at_target.

#minimize { 1@3, X : stuck(X) }.
#minimize { 1@2, X, T : go(X, T, _), not done(X, T, _) }.
#minimize { Q@1, X, T : go(X, T, W), not done(X, T, _), wprio(W, Q) }.

#show stuck/1.
