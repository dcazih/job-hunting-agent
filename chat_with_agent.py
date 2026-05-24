# chat_with_agent.py

from job_agent import create_job_agent


def extract_last_message(result):
    messages = result.get("messages", [])

    if not messages:
        return str(result)

    return messages[-1].content


def main():
    agent = create_job_agent()

    print("Interactive Job Agent")
    print("Type 'exit' or 'quit' to stop.")

    conversation = []

    while True:
        user_input = input("\nYou: ").strip()

        if user_input.lower() in ["exit", "quit"]:
            break

        conversation.append({
            "role": "user",
            "content": user_input
        })

        result = agent.invoke({
            "messages": conversation
        })

        assistant_message = extract_last_message(result)

        print("\nAgent:")
        print(assistant_message)

        conversation.append({
            "role": "assistant",
            "content": assistant_message
        })


if __name__ == "__main__":
    main()