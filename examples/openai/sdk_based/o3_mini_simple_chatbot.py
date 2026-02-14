from openai import OpenAI

client = OpenAI(
    api_key="random+whatever", base_url="http://localhost:44498/v1"
)  # replace the base url with actual argo proxy port and ip, such as lambda5:44497
model = "argo:gpt-o3-mini"

# Initialize conversation history
messages = [{"role": "system", "content": "You are a helpful assistant."}]


def get_user_input():
    print("\nUser: ", end="")
    return input()


def display_response(response):
    print("\nAssistant: ", end="")
    for chunk in response:
        content = chunk.choices[0].delta.content or ""
        print(content, end="", flush=True)
    print()


def main():
    print("Chat with the assistant! Type 'exit' to end the conversation.")

    while True:
        user_input = get_user_input()

        if user_input.lower() == "exit":
            break

        # Add user message to history
        messages.append({"role": "user", "content": user_input})

        # Get assistant response
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            stream=True,
        )

        # Display response and add to history
        assistant_response = ""
        for chunk in response:
            content = chunk.choices[0].delta.content or ""
            assistant_response += content
            print(content, end="", flush=True)
        print()

        # Add assistant response to history
        messages.append({"role": "assistant", "content": assistant_response})


if __name__ == "__main__":
    main()
