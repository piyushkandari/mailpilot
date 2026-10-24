"""Compile the LangGraph ReAct loop with Reflection."""
from langgraph.graph import StateGraph, END
from mail_pilot.agent.state import AgentState
from mail_pilot.agent.nodes import (
    think_node, act_node, finalize_node, route_after_think,
    critic_node, route_after_critic, revise_node
)

def build_agent():
    workflow = StateGraph(AgentState)

    workflow.add_node("think", think_node)
    workflow.add_node("act", act_node)
    workflow.add_node("critic", critic_node)
    workflow.add_node("revise", revise_node)
    workflow.add_node("finalize", finalize_node)

    workflow.set_entry_point("think")

    # Think -> Act or Critic
    workflow.add_conditional_edges(
        "think",
        route_after_think,
        {
            "act": "act",
            "critic": "critic"
        }
    )

    # Act always loops back to Think
    workflow.add_edge("act", "think")

    # Critic -> Finalize or Revise
    workflow.add_conditional_edges(
        "critic",
        route_after_critic,
        {
            "finalize": "finalize",
            "revise": "revise"
        }
    )

    # Revise loops back to Critic
    workflow.add_edge("revise", "critic")

    workflow.add_edge("finalize", END)

    return workflow.compile()