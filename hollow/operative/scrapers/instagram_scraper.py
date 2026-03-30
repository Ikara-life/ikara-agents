"""
Instagram scraper using Instaloader (free, open source, no API key).
GitHub: https://github.com/instaloader/instaloader

2FA / OTP support:
  - On first run, if Instagram requires a 2FA code, the agent pauses,
    prints a clear prompt to the terminal, and waits for you to type the OTP.
  - After successful login the session is saved to disk.
  - All subsequent runs load the saved session — no login or OTP ever again.
"""

import time
import logging
import random

log = logging.getLogger(__name__)

HASHTAG_MAP = {
    "gym":          ["gym", "gymlife", "fitnessclub", "gymstudio"],
    "pilates":      ["pilates", "pilateslove", "pilatestudio", "reformerpilates"],
    "yoga":         ["yogastudio", "yoga", "yogalife", "hathayoga"],
    "crossfit":     ["crossfit", "crossfitgym", "crossfitlife"],
    "fitness":      ["fitnessstudio", "fitnesscentre", "personaltrainer", "fitnesstraining"],
    "zumba":        ["zumba", "zumbaclass", "zumbafitness"],
    "dance":        ["dancestudio", "danceclass", "danceacademy"],
    "martial arts": ["martialarts", "karate", "mma", "boxing"],
}


class InstagramScraper:
    def __init__(self, ig_username: str = "", ig_password: str = ""):
        self.ig_username = ig_username
        self.ig_password = ig_password
        self._loader = None

    # ── Loader / login ───────────────────────────────────────────────────────

    def _get_loader(self):
        """
        Lazy-init Instaloader with login + full 2FA/OTP handling.

        Flow:
          1. Try loading a saved session file  →  no login needed at all.
          2. No session: attempt fresh login with username + password.
          3. Instagram triggers 2FA  →  pause and prompt for OTP in terminal.
          4. Complete two_factor_login() with the entered code.
          5. Save session to disk — future runs always skip to step 1.
        """
        if self._loader:
            return self._loader

        import instaloader

        L = instaloader.Instaloader(
            download_pictures=False,
            download_videos=False,
            download_video_thumbnails=False,
            download_geotags=False,
            download_comments=False,
            save_metadata=False,
            compress_json=False,
            quiet=True,
            request_timeout=20,
        )

        if not self.ig_username or not self.ig_password:
            log.warning(
                "Instagram: no credentials set — running without login.\n"
                "Set IG_USERNAME + IG_PASSWORD in .env for better results."
            )
            self._loader = L
            return L

        # Step 1: try saved session ──────────────────────────────────────────
        try:
            L.load_session_from_file(self.ig_username)
            log.info(f"Instagram: loaded saved session for @{self.ig_username} ✓")
            self._loader = L
            return L
        except FileNotFoundError:
            log.info(f"Instagram: no saved session — logging in as @{self.ig_username}")
        except Exception as e:
            log.warning(f"Instagram: saved session invalid ({e}) — re-logging in")

        # Step 2: fresh login ────────────────────────────────────────────────
        try:
            L.login(self.ig_username, self.ig_password)
            L.save_session_to_file()
            log.info(f"Instagram: logged in as @{self.ig_username} ✓  (session saved)")

        except instaloader.exceptions.TwoFactorAuthRequiredException:
            # Step 3-5: 2FA challenge — prompt user for OTP ──────────────────
            log.info("Instagram: 2FA required — prompting for OTP...")
            self._handle_2fa(L)

        except instaloader.exceptions.BadCredentialsException:
            log.error(
                "Instagram: wrong username or password.\n"
                "Check IG_USERNAME and IG_PASSWORD in your .env file."
            )
        except instaloader.exceptions.ConnectionException as e:
            log.error(f"Instagram: connection error during login: {e}")
        except Exception as e:
            log.warning(f"Instagram: login failed ({e}) — continuing without login")

        self._loader = L
        return L

    def _handle_2fa(self, L) -> None:
        """
        Prompt the terminal for a 6-digit OTP, complete two_factor_login(),
        and save the session. Retries up to 3 times on a wrong code.

        Works with SMS codes, email codes, and authenticator-app TOTPs.
        If running non-interactively (cron / CI) it logs a clear message
        telling the user to do a manual first-run to save a session.
        """
        import instaloader

        # Flush buffered log lines so the prompt appears below them cleanly
        for handler in logging.getLogger().handlers:
            handler.flush()

        print("\n" + "=" * 56)
        print("  Instagram two-factor authentication (2FA)")
        print("=" * 56)
        print(f"  Account  : @{self.ig_username}")
        print("  Open Instagram on your phone (or check your email /")
        print("  authenticator app) and enter the 6-digit code below.")
        print("=" * 56)

        for attempt in range(1, 4):
            try:
                otp = input(f"  OTP code (attempt {attempt}/3): ").strip()

                if not otp.isdigit() or len(otp) != 6:
                    print("  ✗  Must be exactly 6 digits — try again.")
                    continue

                L.two_factor_login(otp)
                L.save_session_to_file()
                print()
                print("  ✓  Login successful!")
                print("  Session saved — you won't be asked for an OTP again")
                print("  on this machine.")
                print("=" * 56 + "\n")
                log.info(
                    f"Instagram: 2FA login successful for @{self.ig_username} "
                    "(session saved to disk)"
                )
                return

            except instaloader.exceptions.BadCredentialsException:
                print("  ✗  Wrong OTP — please try again.")
            except instaloader.exceptions.TwoFactorAuthRequiredException:
                print("  ✗  OTP rejected by Instagram — please try again.")
            except EOFError:
                # Non-interactive environment (cron, Docker without TTY, etc.)
                print()
                log.error(
                    "Instagram: 2FA required but no terminal is available.\n"
                    "Run the agent once interactively first:\n"
                    "  uv run operative\n"
                    "Complete the OTP prompt to save a session file, then you\n"
                    "can schedule or automate subsequent runs safely."
                )
                return
            except Exception as e:
                log.error(f"Instagram: unexpected error during 2FA: {e}")
                return

        print("  ✗  Too many failed attempts — continuing without login.")
        print("=" * 56 + "\n")
        log.warning("Instagram: 2FA failed after 3 attempts — running without login")

    # ── Public search API ────────────────────────────────────────────────────

    def search(self, keyword: str, location: str = "", max_results: int = 50) -> list[dict]:
        """Search hashtags and return profile dicts for matching accounts."""
        import instaloader

        L = self._get_loader()
        hashtags = self._keyword_to_hashtags(keyword, location)
        log.info(f"  Instagram hashtags for '{keyword}': {hashtags}")

        usernames_seen: set[str] = set()
        profiles: list[dict] = []

        for tag in hashtags:
            if len(profiles) >= max_results:
                break
            try:
                log.info(f"  Scraping #{tag} ...")
                posts = instaloader.Hashtag.from_name(L.context, tag).get_posts()
                collected_posts = 0

                for post in posts:
                    if len(profiles) >= max_results or collected_posts >= 25:
                        break

                    owner = post.owner_username
                    collected_posts += 1

                    if owner in usernames_seen:
                        continue
                    usernames_seen.add(owner)

                    profile_data = self._fetch_profile(L, owner)
                    if profile_data:
                        profiles.append(profile_data)

                    time.sleep(random.uniform(2.5, 5.0))

            except instaloader.exceptions.QueryReturnedNotFoundException:
                log.warning(f"  Hashtag #{tag} not found — skipping")
            except instaloader.exceptions.TooManyRequestsException:
                log.warning("  Rate limit hit — sleeping 90s...")
                time.sleep(90)
            except Exception as e:
                log.error(f"  Error scraping #{tag}: {e}")

            time.sleep(random.uniform(6, 12))

        log.info(f"  Instagram: collected {len(profiles)} profiles for '{keyword}'")
        return profiles

    def get_profiles_by_username(self, usernames: list[str]) -> list[dict]:
        """Directly fetch profiles for a given list of usernames."""
        L = self._get_loader()
        results = []
        for username in usernames:
            data = self._fetch_profile(L, username)
            if data:
                results.append(data)
            time.sleep(random.uniform(2, 4))
        return results

    # ── Internal helpers ─────────────────────────────────────────────────────

    def _fetch_profile(self, L, username: str) -> dict | None:
        import instaloader
        try:
            profile = instaloader.Profile.from_username(L.context, username)
            data = {
                "username":             profile.username,
                "fullName":             profile.full_name or "",
                "biography":            profile.biography or "",
                "externalUrl":          profile.external_url or "",
                "followersCount":       profile.followers,
                "followingCount":       profile.followees,
                "postsCount":           profile.mediacount,
                "isBusinessAccount":    profile.is_business_account,
                "businessEmail":        profile.business_email or "",
                "businessPhone":        profile.business_phone or "",
                "businessCategoryName": profile.business_category_name or "",
                "profilePicUrl":        profile.profile_pic_url,
                "isVerified":           profile.is_verified,
            }
            log.debug(
                f"  @{username}: {profile.followers} followers | "
                f"biz={profile.is_business_account} | "
                f"email={data['businessEmail'] or '—'}"
            )
            return data

        except instaloader.exceptions.ProfileNotExistsException:
            log.debug(f"  @{username} not found")
            return None
        except instaloader.exceptions.TooManyRequestsException:
            log.warning("  Rate limited on profile fetch — sleeping 90s...")
            time.sleep(90)
            return None
        except Exception as e:
            log.debug(f"  Could not fetch @{username}: {e}")
            return None

    def _keyword_to_hashtags(self, keyword: str, location: str = "") -> list[str]:
        kw = keyword.lower().strip()
        loc = location.lower().replace(" ", "").strip()

        base_tags = []
        for key, tags in HASHTAG_MAP.items():
            if key in kw or kw in key:
                base_tags.extend(tags)

        if not base_tags:
            base_tags = [kw.replace(" ", ""), kw.replace(" ", "") + "studio"]

        location_tags = []
        if loc:
            for tag in base_tags[:2]:
                location_tags.append(tag + loc)

        return list(dict.fromkeys(base_tags + location_tags))[:6]
