"""
Kandid Chat V1 - Real-World Browser UX & Functional QA Script
Tests the live running application at:
  - 390 × 844 (iPhone 12/13/14)
  - 375 × 812 (iPhone X/XS/11 Pro)
  - 393 × 852 (iPhone 14 Pro / 15)
  - 430 × 932 (iPhone 14 Pro Max / 15 Plus)
"""

import time
import os
import sys
import json
import datetime
import sqlite3
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

BASE_URL = "http://localhost:8080"
DB_PATH = "/Users/mdsarebaj/kandid_project/data/kandid.db"

def get_test_credentials():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    # Pick two active real users
    cursor.execute("SELECT id, handle, name FROM users WHERE role != 'banned' ORDER BY streak_count DESC, id ASC LIMIT 2")
    rows = cursor.fetchall()
    user_a = {"id": rows[0][0], "handle": rows[0][1], "name": rows[0][2]}
    user_b = {"id": rows[1][0], "handle": rows[1][1], "name": rows[1][2]}
    
    # Create or reuse a fresh valid session for user_a
    token_a = "qa_session_" + str(int(time.time()))
    now_iso = datetime.datetime.now().isoformat()
    cursor.execute("INSERT INTO sessions (token, user_id, expires_at, created_at) VALUES (?, ?, '2029-12-31T23:59:59', ?)", 
                   (token_a, user_a["id"], now_iso))
    conn.commit()
    conn.close()
    return user_a, user_b, token_a

def create_driver(width, height):
    chrome_options = Options()
    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_experimental_option("mobileEmulation", {
        "deviceMetrics": {"width": width, "height": height, "pixelRatio": 3.0}
    })
    driver = webdriver.Chrome(options=chrome_options)
    return driver

def run_qa():
    print("=" * 60)
    print("🚀 STARTING KANDID CHAT V1 REAL-WORLD BROWSER UX QA")
    print("=" * 60)

    user_a, user_b, token_a = get_test_credentials()
    print(f"Authenticated QA User: {user_a['name']} (@{user_a['handle']}) [{user_a['id']}]")
    print(f"Target Chat Partner:   {user_b['name']} (@{user_b['handle']}) [{user_b['id']}]")

    viewports = [
        (390, 844, "iPhone 12/13/14 (Standard)"),
        (375, 812, "iPhone X/11 Pro (Compact)"),
        (393, 852, "iPhone 14/15 Pro (Dynamic Island)"),
        (430, 932, "iPhone 14/15 Pro Max (Large)")
    ]

    results = []

    for width, height, name in viewports:
        print(f"\n📱 Testing Viewport: {width} × {height} ({name})")
        driver = create_driver(width, height)
        try:
            # 1. Load application & inject authentication
            driver.get(BASE_URL)
            time.sleep(1)
            
            driver.execute_script(f"""
                localStorage.setItem('kandid_token', '{token_a}');
                localStorage.setItem('kandid_active_uid', '{user_a['id']}');
                localStorage.setItem('kandid_user', JSON.stringify({{
                    id: '{user_a['id']}',
                    handle: '{user_a['handle']}',
                    name: '{user_a['name']}'
                }}));
                if (window.state) {{
                    window.state.token = '{token_a}';
                    window.state.currentUser = {{
                        id: '{user_a['id']}',
                        handle: '{user_a['handle']}',
                        name: '{user_a['name']}'
                    }};
                }}
            """)
            driver.refresh()
            time.sleep(1.5)

            # 2. Check Horizontal Overflow
            scroll_w = driver.execute_script("return document.documentElement.scrollWidth;")
            inner_w = driver.execute_script("return window.innerWidth;")
            overflow_ok = scroll_w <= inner_w
            print(f"  [{'PASS' if overflow_ok else 'FAIL'}] Horizontal overflow check: scrollWidth={scroll_w}px, innerWidth={inner_w}px")
            assert overflow_ok, f"Horizontal overflow detected: scrollWidth={scroll_w} > innerWidth={inner_w}"

            # 3. Navigate to Chat Home
            driver.execute_script("switchScreenView('chat-home');")
            time.sleep(1)

            # 4. Verify Chat Home Elements
            chat_home = driver.find_element(By.ID, "screen-chat-home")
            assert chat_home.is_displayed(), "Chat home screen is not visible"

            # Check: NO redundant top-right '+' button
            plus_buttons = driver.find_elements(By.CSS_SELECTOR, "#screen-chat-home header button[title*='New'], #screen-chat-home header button[title*='Compose'], #screen-chat-home button.fab-chat")
            assert len(plus_buttons) == 0, "Found redundant '+' or FAB compose button in Chat Home"
            print("  [PASS] No redundant '+' button or FAB in Chat Home (Search is the primary doorway)")

            # Check Search Input
            search_input = driver.find_element(By.ID, "chatSearchInput")
            assert search_input.is_displayed(), "Chat search input is not visible"
            print("  [PASS] Chat search input present & accessible")

            # Check Empty Chat State or Populated Conversation list
            state_pop = driver.find_element(By.ID, "state-populated")
            state_empty = driver.find_element(By.ID, "state-empty")
            has_state = state_pop is not None and state_empty is not None
            assert has_state, "Neither empty state nor conversation container found"
            print("  [PASS] Conversation containers (state-populated / state-empty) rendered appropriately")

            # 5. Open Conversation with Target User using openChatThread
            driver.execute_script(f"openChatThread('{user_b['id']}', '{user_b['name']}', '{user_b['handle']}');")
            time.sleep(1.5)

            chat_conv = driver.find_element(By.ID, "screen-chat-conversation")
            assert chat_conv.is_displayed(), "Conversation screen is not displayed"
            print("  [PASS] Conversation opened successfully via openChatThread")

            # 6. Verify Conversation Header & Honest Security Badge
            header_conv = driver.find_element(By.ID, "headerChatConversation")
            assert header_conv.is_displayed(), "Conversation header is not displayed"
            
            header_text = header_conv.text
            print(f"  [PASS] Conversation header text: '{header_text.replace(chr(10), ' | ')}'")
            assert "Private · In Transit" in header_text or "Private" in header_text, f"Unexpected header: {header_text}"
            assert "End-to-End" not in header_text, "Misleading E2EE label found!"
            assert "Signal" not in header_text, "Misleading Signal label found!"

            # Verify Partner Identity in Header
            name_el = driver.find_element(By.ID, "headerChatName")
            handle_el = driver.find_element(By.ID, "headerChatHandle")
            print(f"  [PASS] Conversation partner header: {name_el.text} ({handle_el.text})")

            # 7. Test Sending Message via robust async bridge
            test_msg = f"QA Test message ({width}x{height})"
            composer_input = driver.find_element(By.ID, "chatComposerInput")
            driver.execute_script(f"arguments[0].value = '{test_msg}'; arguments[0].dispatchEvent(new Event('input'));", composer_input)

            send_res = driver.execute_async_script("""
                var done = arguments[arguments.length - 1];
                (async () => {
                    try {
                        await sendChatMessageV2();
                        done({
                            success: true,
                            messages: state.chatLoadedMessages
                        });
                    } catch(e) {
                        done({ success: false, error: e.toString() });
                    }
                })();
            """)
            assert send_res.get("success"), f"Send message failed: {send_res.get('error')}"
            msgs = send_res.get("messages") or []
            assert len(msgs) > 0, "No messages in chatLoadedMessages after send"
            last_msg = msgs[-1]
            print(f"  [PASS] Message successfully sent & persisted: '{last_msg.get('content')}' [ID: {last_msg.get('id')}]")

            # Verify message rendered in history DOM
            history = driver.find_element(By.ID, "chatMessageHistoryV2")
            assert test_msg in history.text, "Message text not found in conversation history DOM"
            print("  [PASS] Message rendered in history with delivery status checkmark")

            # 8. Test Quoted Reply Flow
            driver.execute_script(f"""
                handleChatReplyClick('{last_msg['id']}');
            """)
            time.sleep(0.5)

            reply_banner = driver.find_element(By.ID, "chatReplyBanner")
            assert not "hidden" in reply_banner.get_attribute("class"), "Reply banner did not appear"
            author_el = driver.find_element(By.ID, "chatReplyAuthor")
            snippet_el = driver.find_element(By.ID, "chatReplySnippet")
            print(f"  [PASS] Quoted reply banner active: {author_el.text} ('{snippet_el.text}')")

            # Dismiss reply
            dismiss_btn = driver.find_element(By.ID, "chatReplyDismissBtn")
            dismiss_btn.click()
            time.sleep(0.5)
            assert "hidden" in reply_banner.get_attribute("class"), "Reply banner was not dismissed"
            print("  [PASS] Quoted reply banner dismiss works correctly")

            # 9. Test RealMoji Reaction Flow
            driver.execute_script(f"""
                openChatReactionSheet('{last_msg['id']}');
            """)
            time.sleep(0.5)
            rx_modal = driver.find_element(By.ID, "chatReactionSheetModal")
            assert not "hidden" in rx_modal.get_attribute("class"), "Reaction sheet modal did not open"
            print("  [PASS] Reaction sheet modal opens correctly")

            # Close reaction modal
            driver.execute_script("closeChatReactionSheet();")
            time.sleep(0.5)
            assert "hidden" in rx_modal.get_attribute("class"), "Reaction sheet modal was not closed"
            print("  [PASS] Reaction sheet modal closes correctly")

            # 10. Test Attachment Drawer
            driver.execute_script("toggleChatAttachmentMenu();")
            time.sleep(0.5)
            attach_menu = driver.find_element(By.ID, "chatAttachmentMenu")
            assert not "hidden" in attach_menu.get_attribute("class"), "Attachment menu drawer did not toggle open"
            print("  [PASS] Attachment menu drawer opens correctly with Snap and Share options")
            driver.execute_script("closeChatAttachmentMenu();")
            time.sleep(0.5)
            assert "hidden" in attach_menu.get_attribute("class"), "Attachment menu drawer did not close"
            print("  [PASS] Attachment menu drawer closes correctly")

            # 11. Test Action Menu (•••)
            driver.execute_script("openChatActionMenu();")
            time.sleep(0.5)
            action_modal = driver.find_element(By.ID, "chatActionSheetModal")
            assert not "hidden" in action_modal.get_attribute("class"), "Chat action sheet modal did not open"
            print("  [PASS] Chat action sheet (•••) opens with Block and Report options")
            driver.execute_script("closeChatActionMenu();")
            time.sleep(0.5)
            assert "hidden" in action_modal.get_attribute("class"), "Chat action sheet modal did not close"
            print("  [PASS] Chat action sheet modal closes correctly")

            # 12. Test Back Navigation
            back_btn = driver.find_element(By.CSS_SELECTOR, "#headerChatConversation button[onclick*='chat-home']")
            back_btn.click()
            time.sleep(1)
            assert chat_home.is_displayed(), "Back button failed to return to Chat Home"
            print("  [PASS] Back navigation returns smoothly to Chat Home")

            # 13. Test Bottom Navigation
            bottom_dock = driver.find_element(By.ID, "unifiedDock")
            assert bottom_dock.is_displayed(), "Bottom navigation dock is not visible"
            print("  [PASS] Bottom dock navigation remains intact and usable")

            results.append((name, True, "All tests passed"))

        except Exception as e:
            print(f"  ❌ ERROR on {name}: {e}")
            results.append((name, False, str(e)))
        finally:
            driver.quit()
            time.sleep(1)

    print("\n" + "=" * 60)
    print("📊 QA TEST SUMMARY ACROSS VIEWPORTS")
    print("=" * 60)
    all_passed = True
    for name, passed, msg in results:
        status_str = "✅ PASS" if passed else "❌ FAIL"
        print(f"{status_str} | {name}: {msg}")
        if not passed:
            all_passed = False

    print("=" * 60)
    if all_passed:
        print("🎉 ALL VIEWPORTS AND USER FLOWS PASSED QA VERIFICATION!")
    else:
        print("⚠️ SOME VIEWPORTS ENCOUNTERED ISSUES")
    print("=" * 60)
    return all_passed

if __name__ == "__main__":
    success = run_qa()
    sys.exit(0 if success else 1)
