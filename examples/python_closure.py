"""Run from the project root: python -m examples.python_closure."""


def make_multiplier(factor):
    print(f"Outer function: configuring a multiplier with factor={factor}")

    def multiply(number):
        # The returned function retains access to factor from this outer call.
        print(f"Inner function: multiplying {number} by {factor}")
        return number * factor

    # No parentheses: return the function without executing it.
    return multiply


if __name__ == "__main__":
    print("1. Create two configured functions; no multiplication happens yet.")
    double = make_multiplier(2)
    triple = make_multiplier(3)

    print("\n2. Execute the returned functions with a new input.")
    print("double(5) =", double(5))
    print("triple(5) =", triple(5))

    print("\nProject connection:")
    print("make_model_node(model_call, tools) configures and returns a node.")
    print("LangGraph later executes that node with the current state.")
