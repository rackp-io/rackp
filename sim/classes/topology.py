# classes/topology.py
# Canonical RACKP scenario topology: every party operates its OWN Keeper
# (Kr=Referee, Kc=Claimant, Ka=Actor), as RACKP requires — independent custody
# and cross-Keeper verification are core properties (RFC-0002 §2.1, §2.5). A single
# shared Keeper is the architectural anti-pattern the protocol warns against and
# would mask routing/ownership bugs, so scenarios build their world through here.
from classes.World import World
from classes.Actor import Actor
from classes.Claimant import Claimant
from classes.Referee import Referee
from classes.Keeper import Keeper


def standard_world(actor_cls=Actor, claimant_cls=Claimant, with_actor=True, publish_profile=True):
    """Build and register the standard topology, returning
    (world, R, A, C, Kr, Kc, Ka). When with_actor is False (e.g. a PoHI flow with
    no Actor), A and Ka are None. actor_cls / claimant_cls select the party
    implementations (Actor, AppealActor, LiarActor, SelectiveClaimant, …) so scenarios
    keep their behavioural variant while sharing the same per-party Keeper wiring."""
    world = World()
    R  = Referee("R",  keeper_name="Kr")
    C  = claimant_cls("C", keeper_name="Kc")
    Kr = Keeper("Kr")
    Kc = Keeper("Kc")
    agents = [R, C, Kr, Kc]

    A = Ka = None
    if with_actor:
        A  = actor_cls("A", keeper_name="Ka")
        Ka = Keeper("Ka")
        agents += [A, Ka]

    for agent in agents:
        world.register(agent)
    if publish_profile:
        R.publish_profile(keeper_name="Kr")
    return world, R, A, C, Kr, Kc, Ka
