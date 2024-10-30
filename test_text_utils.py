from unittest import TestCase

from text_utils import common_prefix_postfix, extract_yt_code


class Test(TestCase):
    def test_common_prefix_postfix(self):

        possible_filenames = ['aaaaaa_111_bbbbbbbbbb[AAAAAAAA].mp3','aaaaaa_212_bbbbbbbbbb[AAAAAAAA].mp3']

        by_video_lookup = {}

        for possible_filename in possible_filenames:
            video_value = extract_yt_code(possible_filename)
            if video_value not in by_video_lookup:
                by_video_lookup[video_value] = []
            by_video_lookup[video_value].append(possible_filename)

        for key, sample_list in by_video_lookup.items():

            prefix, postfix = common_prefix_postfix(sample_list)

            print(prefix)
            print(postfix)

        self.fail()
