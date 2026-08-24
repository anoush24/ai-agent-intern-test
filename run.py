import uuid
from app.agents.orchestrator import handle_turn


def main():
    session_id = str(uuid.uuid4())
    print("Aster & Row support agent (CLI). Type 'exit' to quit, 'reset' for a new session.\n")
    while True:
        user_input = input("You: ").strip()
        if not user_input:
            continue
        if user_input.lower() == "exit":
            break
        if user_input.lower() == "reset":
            session_id = str(uuid.uuid4())
            print("(new session started)\n")
            continue

        result = handle_turn(session_id, user_input)
        print(f"\nAgent: {result['answer']}")
        if result["sources"]:
            print(f"Sources: {', '.join(result['sources'])}")
        if result["handoff"]:
            print("⚠ Recommending human assistance for this request.")
        print()


if __name__ == "__main__":
    main()