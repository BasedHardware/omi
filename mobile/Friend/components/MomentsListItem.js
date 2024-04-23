import React from 'react';
import {ListItem} from 'react-native-elements';
import Swipeable from 'react-native-gesture-handler/Swipeable';
import {Text, TouchableOpacity} from 'react-native';
const MomentListItem = ({item, onItemPress, onItemDelete}) => {
  console.log(item)
  const renderRightActions = () => (
    <TouchableOpacity onPress={() => onItemDelete(item)}>
      <Text>Delete</Text>
    </TouchableOpacity>
  );

  const formatDate = date => {
    return new Date(date).toLocaleDateString('en-US', {
      year: 'numeric',
      month: 'long',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
      hour12: true,
    });
  };

  return (
    <Swipeable renderRightActions={renderRightActions}>
      <ListItem onPress={() => onItemPress(item)} bottomDivider>
        <ListItem.Content>
          <ListItem.Title>{item.text.substring(0, 30) + '...'}</ListItem.Title>
          <ListItem.Subtitle>
            {formatDate(item.date)}
          </ListItem.Subtitle>
        </ListItem.Content>
        <ListItem.Chevron />
      </ListItem>
    </Swipeable>
  );
};

export default MomentListItem;
