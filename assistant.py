from core.orchestrator import run_react_loop
from engine.wake_word import wake_word_detection
from engine.stt import speech_to_text
from engine.tts import text_to_speech

def main():
    print("[Initializing ...]")
    oww_model = Model(wakeword_models=["jarvis"], inference_framework="onnx")
    
    print("\n===============================")
    print("Pipeline Ready. Say 'Jarvis' to wake me.")
    print("\n===============================")

    while True:
        # Phase 1: Wake Word
        wake_word_detection(oww_model) 
       
        # Phase 2: Active Listening
        try:
            user_text = speech_to_text(recognizer)

            print(f"[Transcribed]: '{user_text}'")

            if not user_text:
                print("[No speech detected. Going back to sleep.]")
                continue

            gemma_reply = run_react_loop(user_text)

            print("[Speaking...]")
            text_to_speech(pipeline, gemma_reply, target_voice)
        except sr.WaitTimeoutError:
            print("[Timed out waiting for a command. Going back to sleep.]")
        except sr.UnknownValueError:
            print("[Didn't catch that! Going back to sleep.]")
        except Exception as e:
            print(f"[Error in pipeline]: {e}")

        print("\n[Sleeping..] Say Jarvis to wake me up.")


if __name__ == "__main__":
    main()
